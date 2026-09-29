"""Playwright 有头浏览器单例 — 通用浏览器能力，用于绕过反爬。

东财 push2 等接口有反爬：程序化访问（requests/curl/无头浏览器）会被识别返回
空数据/断开，只有「有头真实浏览器」能通过。Playwright 同步 API 绑定创建线程，
不能跨线程调用，而 Flask 多线程处理请求，所以用「专用 worker 线程 + 队列」串行。

对外能力：
- init_browser():     服务器启动时调用，提前在后台拉起浏览器进程并预热；
- jsonp_get(url):     JSONP 方式请求（板块资金排行榜/成分股用）；
- browser_get_text(url): 打开网页返回 HTML 文本（供其他数据源复用）。

浏览器进程在 worker 线程启动时即拉起（不再懒加载），首次请求无需等待冷启动。
浏览器被手动关闭后会自动重启；程序退出时通过 atexit 优雅关闭。
"""
import atexit
import queue
import threading

from playwright.sync_api import sync_playwright

_UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
       '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36')

# 预热页：先访问一次东财网页让浏览器拿到 cookie，避免首次请求被反爬拦截
_DEFAULT_WARMUP_URL = 'https://data.eastmoney.com/bkzj/hy.html'

# JSONP 请求的浏览器端 JS：用 script 标签 + cb 回调拿数据（东财跨域只对 JSONP 放行）
_JSONP_JS = """
async ({url, timeout}) => {
    return await new Promise((resolve) => {
        const cb = '__jsonp_' + Date.now() + '_' + Math.floor(Math.random() * 100000);
        window[cb] = (data) => {
            resolve(data);
            try { delete window[cb]; } catch (e) {}
        };
        const s = document.createElement('script');
        s.src = url + (url.indexOf('?') >= 0 ? '&' : '?') + 'cb=' + cb;
        s.onerror = () => resolve({__error__: 'script load failed'});
        document.head.appendChild(s);
        setTimeout(() => resolve({__error__: 'jsonp timeout'}), timeout);
    });
}
"""

# 任务类型
_T_JSONP = 'jsonp'
_T_GET_TEXT = 'get_text'

_queue = queue.Queue()
_worker = None
_lock = threading.Lock()


def _worker_loop():
    """浏览器工作线程：启动即拉起浏览器并预热，然后串行处理所有任务。

    浏览器被手动关闭后，evaluate/goto 会抛异常，这里把 browser 置空，下次任务
    _ensure_browser 检测到 is_connected 为 False 会自动重新拉起。
    """
    pw = sync_playwright().start()
    browser = None
    page = None

    def _ensure_browser():
        nonlocal browser, page
        if browser is not None and browser.is_connected():
            return page
        if browser is not None:
            try:
                browser.close()
            except Exception:
                pass
        browser = pw.chromium.launch(channel='msedge', headless=False)
        context = browser.new_context(
            user_agent=_UA,
            viewport={'width': 1920, 'height': 1080},
        )
        page = context.new_page()
        page.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
        return page

    def _warmup():
        nonlocal page
        try:
            page.goto(_DEFAULT_WARMUP_URL, wait_until='domcontentloaded', timeout=20000)
            page.wait_for_timeout(3000)
        except Exception:
            pass

    # 启动即拉起浏览器并预热（后台进行；失败不退出，后续任务通过 _ensure_browser 重试）
    try:
        _ensure_browser()
        _warmup()
    except Exception:
        pass

    try:
        while True:
            task = _queue.get()
            if task is None:  # 关闭信号
                break
            task_type, payload, holder = task
            try:
                page = _ensure_browser()
                if task_type == _T_JSONP:
                    holder['data'] = page.evaluate(_JSONP_JS, payload)
                else:  # _T_GET_TEXT
                    page.goto(payload['url'], wait_until='domcontentloaded',
                              timeout=payload.get('timeout', 20000))
                    holder['data'] = page.content()
            except Exception as e:
                holder['data'] = {'__error__': str(e)}
                # 浏览器可能被手动关闭：关掉失效实例，下次 _ensure_browser 会重启
                if browser is not None:
                    try:
                        browser.close()
                    except Exception:
                        pass
                browser = None
                page = None
            finally:
                holder['event'].set()
    finally:
        if browser is not None:
            try:
                browser.close()
            except Exception:
                pass
        try:
            pw.stop()
        except Exception:
            pass


def _ensure_worker():
    """确保浏览器工作线程已启动（幂等）"""
    global _worker
    with _lock:
        if _worker is None or not _worker.is_alive():
            _worker = threading.Thread(target=_worker_loop, daemon=True)
            _worker.start()


def _submit(task_type, payload, timeout):
    """提交任务到浏览器 worker，阻塞等待结果；失败返回 {'__error__': ...}"""
    _ensure_worker()
    holder = {'data': None, 'event': threading.Event()}
    _queue.put((task_type, payload, holder))
    holder['event'].wait(timeout=timeout + 15000)
    if not holder['event'].is_set():
        return {'__error__': 'browser worker timeout'}
    return holder['data']


def init_browser():
    """服务器启动时调用：后台拉起浏览器进程并预热。

    立即返回（浏览器在 worker 线程内后台启动），首次请求若浏览器尚未就绪会
    排队等待。幂等：重复调用不会重复启动。
    """
    _ensure_worker()


def jsonp_get(url, timeout=8000):
    """JSONP 方式请求，返回解析后的 JSON（dict/list）。失败返回 {'__error__': ...}。"""
    return _submit(_T_JSONP, {'url': url, 'timeout': timeout}, timeout)


def browser_get_text(url, timeout=20000):
    """用浏览器打开网页并返回 HTML 文本。失败返回 {'__error__': ...}。"""
    return _submit(_T_GET_TEXT, {'url': url, 'timeout': timeout}, timeout)


def _close():
    """程序退出时通知浏览器工作线程关闭，释放进程与内存"""
    try:
        _queue.put(None)
    except Exception:
        pass


atexit.register(_close)
