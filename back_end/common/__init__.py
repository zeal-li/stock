"""共享配置和工具"""
import os
import requests as _requests
from requests.adapters import HTTPAdapter

# 禁用系统代理
os.environ['no_proxy'] = '*'
os.environ['NO_PROXY'] = '*'
os.environ['HTTP_PROXY'] = ''
os.environ['HTTPS_PROXY'] = ''
os.environ['http_proxy'] = ''
os.environ['https_proxy'] = ''
REQUEST_PROXIES = {'http': None, 'https': None}

# 浏览器伪装请求头（避免被 WAF 拦截）
BROWSER_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    'Accept-Encoding': 'gzip, deflate, br',
    'Cache-Control': 'no-cache',
    'Connection': 'keep-alive',
    'Pragma': 'no-cache',
    'Referer': 'https://finance.qq.com/',
    'Origin': 'https://finance.qq.com',
    'Sec-Fetch-Dest': 'empty',
    'Sec-Fetch-Mode': 'cors',
    'Sec-Fetch-Site': 'cross-site',
    'Sec-Ch-Ua': '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
    'Sec-Ch-Ua-Mobile': '?0',
    'Sec-Ch-Ua-Platform': '"Windows"',
}


def make_http_session():
    """创建一个复用 TCP 连接的 Session（keep-alive 连接池）。

    避免每次请求都新建连接、短时间高频裸连被远端风控掐断。
    """
    s = _requests.Session()
    s.proxies = REQUEST_PROXIES
    adapter = HTTPAdapter(pool_connections=20, pool_maxsize=20, max_retries=0)
    s.mount('http://', adapter)
    s.mount('https://', adapter)
    return s


# 全局共享 Session：行情/资金流等高频轮询接口复用，避免频繁握手
HTTP_SESSION = make_http_session()


def warmup_eastmoney_session():
    """预热东财共享 Session：先访问一次东财页面，让 Session 获取并保存 Cookie。
    之后所有行情/资金流请求会自动携带该 Cookie，更接近真实浏览器访问特征，
    降低被风控识别的概率。连接层预热失败仅记录日志，不影响后续请求（各接口
    仍各自带 User-Agent/Referer，Cookie 只是增强伪装）。"""
    try:
        HTTP_SESSION.get('https://quote.eastmoney.com/', timeout=10)
    except Exception as e:
        print(f'[warmup] 东财 Cookie 预热失败: {e}')
