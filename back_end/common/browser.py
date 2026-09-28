"""Playwright 有头浏览器单例 — 用于绕过东财 push2 反爬。

东财对 push2 系接口做了反爬：程序化访问（requests/curl/无头浏览器）会被
识别并返回空数据/断开连接，只有「有头真实浏览器」能通过。

Playwright 的同步 API 绑定创建线程（greenlet），不能跨线程调用。而 Flask
多线程处理请求，所以这里用「专用浏览器工作线程 + 队列」：
- 所有浏览器操作（启动 / JSONP 请求）都在同一个 worker 线程里串行执行；
- 业务线程通过队列提交请求、用 Event 等待结果；
- 浏览器进程只在首次使用时懒加载启动，程序退出时通过 atexit 优雅关闭。
"""
import atexit
import queue
import threading

from playwright.sync_api import sync_playwright

_UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
       '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36')

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

_queue = queue.Queue()
_worker = None
_lock = threading.Lock()


def _worker_loop():
    """浏览器工作线程：启动浏览器并在本线程内串行处理所有请求。

    浏览器被手动关闭后，evaluate 会抛异常，这里把 browser 置空，下次请求
    会自动重新拉起浏览器（_ensure_browser 里检测 is_connected）。
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
        # 预热：先访问一次东财网页让浏览器拿到 cookie，避免首次请求被反爬拦截
        try:
            page.goto('https://data.eastmoney.com/bkzj/hy.html',
                      wait_until='domcontentloaded', timeout=20000)
            page.wait_for_timeout(3000)
        except Exception:
            pass
        return page

    try:
        while True:
            url, timeout, holder = _queue.get()
            if url is None:  # 关闭信号
                break
            try:
                page = _ensure_browser()
                holder['data'] = page.evaluate(_JSONP_JS, {'url': url, 'timeout': timeout})
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


def jsonp_get(url, timeout=8000):
    """用浏览器 JSONP 方式请求东财接口，返回解析后的 JSON（dict）。

    失败返回 {'__error__': ...}。浏览器线程尚未就绪时等待最多 30 秒。
    """
    _ensure_worker()
    holder = {'data': None, 'event': threading.Event()}
    _queue.put((url, timeout, holder))
    holder['event'].wait(timeout=timeout + 15000)
    if not holder['event'].is_set():
        return {'__error__': 'browser worker timeout'}
    return holder['data']


def _close():
    """程序退出时通知浏览器工作线程关闭，释放进程与内存"""
    try:
        _queue.put((None, 0, None))
    except Exception:
        pass


atexit.register(_close)
