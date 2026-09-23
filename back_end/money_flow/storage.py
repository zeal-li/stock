"""缓存管理和后台轮询 — SQLite 持久化"""
import datetime
import json
import os
import random
import sqlite3
import time
from common import REQUEST_PROXIES
from common.utils import is_a_trading_time, effective_today_str

# 数据库路径（与 watchlist.db 同级在 data/ 目录下）
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'money_flow.db')


def _db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute('CREATE TABLE IF NOT EXISTS market_data (key TEXT PRIMARY KEY, value TEXT NOT NULL, meta TEXT)')
    conn.commit()
    return conn


def db_get(key):
    """读取缓存，返回 (value, meta) 或 None"""
    conn = _db()
    row = conn.execute('SELECT value, meta FROM market_data WHERE key = ?', (key,)).fetchone()
    conn.close()
    if row:
        val = json.loads(row[0])
        meta = row[1]
        # meta 可能是时间戳(float)或日期字符串
        try:
            meta = float(meta)
        except (ValueError, TypeError):
            pass
        return (val, meta)
    return None


def db_set(key, value, meta=''):
    """写入缓存，meta 存时间戳或日期字符串"""
    conn = _db()
    conn.execute('INSERT OR REPLACE INTO market_data (key, value, meta) VALUES (?, ?, ?)',
                 (key, json.dumps(value, ensure_ascii=False), str(meta)))
    conn.commit()
    conn.close()


def db_has(key):
    """判断 key 是否存在"""
    conn = _db()
    row = conn.execute('SELECT 1 FROM market_data WHERE key = ?', (key,)).fetchone()
    conn.close()
    return row is not None


# 东方财富通用配置
_EM_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Referer': 'https://data.eastmoney.com/',
}
_EM_UT = 'bd1d9ddb04089700cf9c27f6f7426281'


def _cached(key, ttl=5):
    """如果 key 在 ttl 秒内已缓存则返回缓存值"""
    row = db_get(key)
    if row:
        val, meta = row
        if isinstance(meta, (int, float)) and time.time() - meta < ttl:
            return val
    return None


def _cache_set(key, val):
    db_set(key, val, time.time())


# ===== 缓存 key 常量 =====
_MAJOR_INDICES_KEY = 'major_indices'
_MARKET_BREADTH_KEY = 'market_breadth'
_SH_MINUTE_KEY = 'sh_minute'
_FUND_FLOW_KEY = 'fund_flow'
_TURNOVER_MINUTE_KEY = 'turnover_minute'
_MARGIN_KEY = 'margin_trading'
_DAILY_CLOSES_KEY = 'daily_closes'


def _is_cache_from_today(cached_row, today_str):
    """检查缓存是否来自今天，兼容 meta 为时间戳(float)或日期字符串"""
    if not cached_row:
        return False
    meta = cached_row[1]
    if isinstance(meta, (int, float)):
        cached_day = datetime.datetime.fromtimestamp(meta).strftime('%Y-%m-%d')
        return cached_day == today_str
    # 日期字符串，直接比较
    return meta == today_str




# =========== 资金流/指数行情更新（接入公共秒级调度器，不再单独开线程） ===========
# 由 app.py 的公共秒级调度器每秒调用一次 check_money_flow_update。
# 不区分快/慢任务：每个 poller 各自维护一个"下次更新时间戳"，到点即执行，
# 并把时间戳推进为 now + 随机间隔（45~75s），错峰避免多个东财请求同一秒突发。

_QUOTE_MIN_INTERVAL = 45   # 行情 poller 最小间隔（秒）
_QUOTE_MAX_INTERVAL = 75   # 行情 poller 最大间隔（秒）


def _rand_interval():
    return random.uniform(_QUOTE_MIN_INTERVAL, _QUOTE_MAX_INTERVAL)


def _next_daily_run_ts():
    """返回下一个凌晨 00:30 的时间戳，每日任务每天只在该点触发一次。"""
    now = datetime.datetime.now()
    target = now.replace(hour=0, minute=30, second=0, microsecond=0)
    if target <= now:
        target += datetime.timedelta(days=1)
    return target.timestamp()


# 各 poller 的下次执行时间戳
_next_major_ts = 0.0      # 主要指数
_next_breadth_ts = 0.0    # 涨跌家数
_next_sh_minute_ts = 0.0  # 上证分时
_next_fund_flow_ts = 0.0  # 资金流
_next_turnover_ts = 0.0   # 成交额
_next_daily_ts = 0.0      # 每日任务检查


def _full_fetch_if_stale():
    """启动初始化：当日缓存缺失时全量抓取一轮行情数据"""
    today = effective_today_str()
    cached = db_get(_MAJOR_INDICES_KEY)
    if _is_cache_from_today(cached, today):
        return
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


def _daily_once():
    """每日任务：融资融券与指数日K收盘价（仅当日缓存缺失时抓取）"""
    from money_flow.margin import _fetch_and_cache_margin
    from money_flow.market import _fetch_and_cache_daily_closes
    today_str = datetime.date.today().strftime('%Y-%m-%d')
    cached_margin = db_get(_MARGIN_KEY)
    if not cached_margin or cached_margin[1] != today_str:
        _fetch_and_cache_margin()
    cached_closes = db_get(_DAILY_CLOSES_KEY)
    if not cached_closes or cached_closes[1] != today_str:
        _fetch_and_cache_daily_closes()


def check_money_flow_update():
    """资金流/指数行情更新检测：由公共秒级调度器每秒调用一次。
    仅交易时段内工作；各 poller 按自己的下次更新时间戳独立判断是否执行，
    到点即执行并把时间戳推进为 now + 随机间隔（错峰，避免同秒突发）。"""
    global _next_major_ts, _next_breadth_ts, _next_sh_minute_ts
    global _next_fund_flow_ts, _next_turnover_ts, _next_daily_ts
    now = time.time()

    # 每日任务独立于交易时段判断：到点(00:30)执行一次，随后推进到下一天 00:30
    if now >= _next_daily_ts:
        _next_daily_ts = _next_daily_run_ts()
        _daily_once()

    if not is_a_trading_time():
        return
    if now >= _next_major_ts:
        _next_major_ts = now + _rand_interval()
        from money_flow.market import _fetch_and_cache_major_indices
        _fetch_and_cache_major_indices()
    if now >= _next_breadth_ts:
        _next_breadth_ts = now + _rand_interval()
        from money_flow.market import _fetch_and_cache_breadth
        _fetch_and_cache_breadth()
    if now >= _next_sh_minute_ts:
        _next_sh_minute_ts = now + _rand_interval()
        from money_flow.market import _fetch_and_cache_sh_minute
        _fetch_and_cache_sh_minute()
    if now >= _next_fund_flow_ts:
        _next_fund_flow_ts = now + _rand_interval()
        from money_flow.fund_flow import _fetch_and_cache_fund_flow
        _fetch_and_cache_fund_flow()
    if now >= _next_turnover_ts:
        _next_turnover_ts = now + _rand_interval()
        from money_flow.turnover import _fetch_and_cache_turnover
        _fetch_and_cache_turnover()


def init_money_flow_update():
    """初始化资金流/指数行情更新（由 app.py 启动时调用）：
    1) 先执行启动初始化：当日数据缺失则全量抓取一轮；
    2) 为各 poller 设置随机错峰的"下次更新时间戳"；
    3) 返回检测函数供公共秒级调度器注册。"""
    global _next_major_ts, _next_breadth_ts, _next_sh_minute_ts
    global _next_fund_flow_ts, _next_turnover_ts, _next_daily_ts
    _full_fetch_if_stale()
    now = time.time()
    _next_major_ts = now + _rand_interval()
    _next_breadth_ts = now + _rand_interval()
    _next_sh_minute_ts = now + _rand_interval()
    _next_fund_flow_ts = now + _rand_interval()
    _next_turnover_ts = now + _rand_interval()
    _next_daily_ts = 0  # 启动后第一次 tick 立即触发 _daily_once，确保当日数据缺失时能立刻补抓
    return check_money_flow_update
