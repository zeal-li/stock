"""缓存管理和后台轮询"""
import datetime
import time
import threading
from common import REQUEST_PROXIES

# 东方财富通用配置
_EM_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Referer': 'https://data.eastmoney.com/',
}
_EM_UT = 'bd1d9ddb04089700cf9c27f6f7426281'

# 简单内存缓存
_cache = {}

def _cached(key, ttl=5):
    """如果 key 在 ttl 秒内已缓存则返回缓存值，否则返回 None"""
    if key in _cache:
        val, ts = _cache[key]
        if time.time() - ts < ttl:
            return val
    return None

def _cache_set(key, val):
    _cache[key] = (val, time.time())


# ===== 缓存 key 常量 =====
_MAJOR_INDICES_KEY = 'major_indices'
_MARKET_BREADTH_KEY = 'market_breadth'
_SH_MINUTE_KEY = 'sh_minute'
_FUND_FLOW_KEY = 'fund_flow'
_TURNOVER_MINUTE_KEY = 'turnover_minute'
_MARGIN_KEY = 'margin_trading'
_DAILY_CLOSES_KEY = 'daily_closes'


def _is_trading_time():
    """判断当前是否在A股交易时段（周一至周五 09:15-11:35, 12:55-15:05）"""
    now = datetime.datetime.now()
    day = now.weekday()
    if day >= 5:
        return False
    t = now.hour * 60 + now.minute
    return (555 <= t <= 695) or (775 <= t <= 905)


def _background_poller():
    """后台线程：启动时立即抓取，之后交易时段按不同频率自动抓取"""
    from money_flow.market import _fetch_and_cache_major_indices, _fetch_and_cache_breadth, _fetch_and_cache_sh_minute, _fetch_and_cache_daily_closes
    from money_flow.fund_flow import _fetch_and_cache_fund_flow
    from money_flow.turnover import _fetch_and_cache_turnover
    from money_flow.margin import _fetch_and_cache_margin

    _fetch_and_cache_major_indices()
    _fetch_and_cache_breadth()
    _fetch_and_cache_sh_minute()
    _fetch_and_cache_fund_flow()
    _fetch_and_cache_turnover()
    _fetch_and_cache_margin()
    _fetch_and_cache_daily_closes()

    _loop_count = 0
    while True:
        time.sleep(5)
        _loop_count += 1
        try:
            if _is_trading_time():
                _fetch_and_cache_major_indices()
                if _loop_count % 12 == 0:
                    _fetch_and_cache_breadth()
                    _fetch_and_cache_sh_minute()
                    _fetch_and_cache_fund_flow()
                    _fetch_and_cache_turnover()
                    _today_str = datetime.date.today().strftime('%Y-%m-%d')
                    _cached_margin = _cache.get(_MARGIN_KEY)
                    if not _cached_margin or _cached_margin[1] != _today_str:
                        _fetch_and_cache_margin()
                    _cached_closes = _cache.get(_DAILY_CLOSES_KEY)
                    if not _cached_closes or _cached_closes[1] != _today_str:
                        _fetch_and_cache_daily_closes()
        except Exception:
            pass


def start_major_indices_poller():
    """启动指数行情后台轮询线程（由 app.py 调用）"""
    t = threading.Thread(target=_background_poller, daemon=True, name='major-indices-poller')
    t.start()
