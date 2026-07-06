"""缓存管理和后台轮询 — SQLite 持久化"""
import datetime
import json
import os
import sqlite3
import time
import threading
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




def _background_poller():
    """后台线程：启动时检查日期，非当日则全量抓取；交易时段按频率刷新"""
    from money_flow.market import _fetch_and_cache_major_indices, _fetch_and_cache_breadth, _fetch_and_cache_sh_minute, _fetch_and_cache_daily_closes
    from money_flow.fund_flow import _fetch_and_cache_fund_flow
    from money_flow.turnover import _fetch_and_cache_turnover
    from money_flow.margin import _fetch_and_cache_margin

    today = effective_today_str()

    # 检查是否已有当日数据（兼容 meta 为时间戳或日期字符串）
    cached = db_get(_MAJOR_INDICES_KEY)
    need_full_fetch = not _is_cache_from_today(cached, today)
    if need_full_fetch:
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
            if is_a_trading_time():
                _fetch_and_cache_major_indices()
                if _loop_count % 12 == 0:
                    _fetch_and_cache_breadth()
                    _fetch_and_cache_sh_minute()
                    _fetch_and_cache_fund_flow()
                    _fetch_and_cache_turnover()
                    _today_str = datetime.date.today().strftime('%Y-%m-%d')
                    cached_margin = db_get(_MARGIN_KEY)
                    if not cached_margin or cached_margin[1] != _today_str:
                        _fetch_and_cache_margin()
                    cached_closes = db_get(_DAILY_CLOSES_KEY)
                    if not cached_closes or cached_closes[1] != _today_str:
                        _fetch_and_cache_daily_closes()
        except Exception:
            pass


def start_major_indices_poller():
    """启动指数行情后台轮询线程（由 app.py 调用）"""
    t = threading.Thread(target=_background_poller, daemon=True, name='major-indices-poller')
    t.start()
