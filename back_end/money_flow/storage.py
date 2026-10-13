"""缓存管理和后台轮询 — SQLite 持久化（按交易日快照）

一张 market_data 表按交易日存完整快照：盘中 poller 实时更新「最新交易日」的对应字段，
每日 17:00 固化任务强制打源覆盖为收盘最终数据；历史日期回看时直接读对应交易日快照。
"""
import datetime
import json
import os
import random
import sqlite3
import threading
import time

from common.utils import is_a_trading_time, is_a_share_trading_day

# 数据库路径（与 watchlist.db 同级在 data/ 目录下）
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'money_flow.db')

# 只保留最近 N 个交易日（与前端日期栏的 30 个交易日对齐）
_KEEP_TRADING_DAYS = 30


def _db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute('''CREATE TABLE IF NOT EXISTS market_data (
        trade_date TEXT PRIMARY KEY,
        data       TEXT NOT NULL,
        updated_at REAL NOT NULL
    )''')
    conn.commit()
    return conn


def _latest_trading_date():
    """返回最近一个A股交易日（YYYY-MM-DD）"""
    d = datetime.date.today()
    while not is_a_share_trading_day(d):
        d -= datetime.timedelta(days=1)
    return d.strftime('%Y-%m-%d')


def snapshot_get(trade_date):
    """读取某交易日快照，返回 dict 或 None"""
    conn = _db()
    row = conn.execute('SELECT data FROM market_data WHERE trade_date = ?', (trade_date,)).fetchone()
    conn.close()
    if row:
        return json.loads(row[0])
    return None


def snapshot_set(trade_date, data):
    """写入某交易日快照（INSERT OR REPLACE）"""
    conn = _db()
    conn.execute('INSERT OR REPLACE INTO market_data (trade_date, data, updated_at) VALUES (?, ?, ?)',
                 (trade_date, json.dumps(data, ensure_ascii=False), time.time()))
    conn.commit()
    conn.close()


def snapshot_update(trade_date, field, value):
    """更新某交易日快照的某个字段（read-modify-write）"""
    data = snapshot_get(trade_date) or {}
    data[field] = value
    snapshot_set(trade_date, data)


def snapshot_field(trade_date, field):
    """读取某交易日快照的某个字段"""
    data = snapshot_get(trade_date)
    if data:
        return data.get(field)
    return None


def save_field(field, value):
    """写入「最新交易日」快照的某个字段（盘中 poller / 每日任务用）"""
    snapshot_update(_latest_trading_date(), field, value)


def get_field(field):
    """读取「最新交易日」快照的某个字段"""
    return snapshot_field(_latest_trading_date(), field)


def snapshot_row(trade_date):
    """读取某交易日快照，返回 (data, updated_at) 或 None"""
    conn = _db()
    row = conn.execute('SELECT data, updated_at FROM market_data WHERE trade_date = ?', (trade_date,)).fetchone()
    conn.close()
    if row:
        return (json.loads(row[0]), row[1])
    return None


def get_field_meta(field):
    """读取「最新交易日」快照的某字段，返回 (value, updated_at) 或 None（供复盘等需要时间戳的场景）"""
    row = snapshot_row(_latest_trading_date())
    if row:
        data, updated_at = row
        if field in data:
            return (data[field], updated_at)
    return None


def cleanup_old_data():
    """删除保留交易日数之前的数据"""
    d = datetime.date.today()
    kept_dates = []
    while len(kept_dates) < _KEEP_TRADING_DAYS:
        if is_a_share_trading_day(d):
            kept_dates.append(d)
        d -= datetime.timedelta(days=1)
    cutoff = kept_dates[-1].strftime('%Y-%m-%d')

    conn = _db()
    r = conn.execute('DELETE FROM market_data WHERE trade_date < ?', (cutoff,)).rowcount
    conn.commit()
    conn.close()
    print(f'[money_flow] 清理过期快照: trade_date < {cutoff}，删除 {r} 条')


# =========== 资金流/指数行情更新（接入公共秒级调度器，不再单独开线程） ===========
# 由 app.py 的公共秒级调度器每秒调用一次 check_money_flow_update。
# 每个 poller 各自维护一个"下次更新时间戳"，到点即执行，
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
_next_distribution_ts = 0.0  # 涨跌分布
_next_sh_minute_ts = 0.0  # 上证分时
_next_fund_flow_ts = 0.0  # 资金流
_next_turnover_ts = 0.0   # 成交额
_next_daily_ts = 0.0      # 每日任务检查


def _full_fetch_if_stale():
    """启动初始化：当日快照缺失时全量抓取一轮行情数据"""
    if snapshot_get(_latest_trading_date()):
        return
    from money_flow.market import _fetch_and_cache_major_indices, _fetch_and_cache_sh_minute, _fetch_and_cache_daily_closes, _fetch_and_cache_distribution
    from money_flow.fund_flow import _fetch_and_cache_fund_flow
    from money_flow.turnover import _fetch_and_cache_turnover
    from money_flow.margin import _fetch_and_cache_margin
    _fetch_and_cache_major_indices()
    _fetch_and_cache_distribution()
    _fetch_and_cache_sh_minute()
    _fetch_and_cache_fund_flow()
    _fetch_and_cache_turnover()
    _fetch_and_cache_margin()
    _fetch_and_cache_daily_closes()


def _daily_once():
    """每日任务（凌晨 00:30）：融资融券与指数日K收盘价"""
    from money_flow.margin import _fetch_and_cache_margin
    from money_flow.market import _fetch_and_cache_daily_closes
    _fetch_and_cache_margin()
    _fetch_and_cache_daily_closes()


def check_money_flow_update():
    """资金流/指数行情更新检测：由公共秒级调度器每秒调用一次。
    仅交易时段内工作；各 poller 按自己的下次更新时间戳独立判断是否执行，
    到点即执行并把时间戳推进为 now + 随机间隔（错峰，避免同秒突发）。"""
    global _next_major_ts, _next_distribution_ts, _next_sh_minute_ts
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
    if now >= _next_distribution_ts:
        _next_distribution_ts = now + _rand_interval()
        from money_flow.market import _fetch_and_cache_distribution
        _fetch_and_cache_distribution()
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
    global _next_major_ts, _next_distribution_ts, _next_sh_minute_ts
    global _next_fund_flow_ts, _next_turnover_ts, _next_daily_ts
    from common import warmup_eastmoney_session
    warmup_eastmoney_session()
    _full_fetch_if_stale()
    now = time.time()
    _next_major_ts = now + _rand_interval()
    _next_distribution_ts = now + _rand_interval()
    _next_sh_minute_ts = now + _rand_interval()
    _next_fund_flow_ts = now + _rand_interval()
    _next_turnover_ts = now + _rand_interval()
    _next_daily_ts = 0  # 启动后第一次 tick 立即触发 _daily_once，确保当日数据缺失时能立刻补抓
    return check_money_flow_update


# =========== 定时任务：每日 17:00 固化 ===========

_AUTO_UPDATE_TIME = (17, 0)
_auto_next_update = None


def _next_update_time(base):
    """返回 base 当天 17:00；若已过则返回次日 17:00"""
    cand = base.replace(hour=_AUTO_UPDATE_TIME[0], minute=_AUTO_UPDATE_TIME[1],
                        second=0, microsecond=0)
    if cand <= base:
        cand = (base + datetime.timedelta(days=1)).replace(
            hour=_AUTO_UPDATE_TIME[0], minute=_AUTO_UPDATE_TIME[1],
            second=0, microsecond=0)
    return cand


def _run_daily_update():
    """每日 17:00 任务：清理过期数据，并强制打源刷新当日快照（覆盖盘中数据为收盘最终数据）。"""
    cleanup_old_data()

    today = datetime.date.today()
    if not is_a_share_trading_day(today):
        print(f'[money_flow] 17:00 任务跳过: {today} 非A股交易日')
        return
    trade_date = today.strftime('%Y-%m-%d')

    # 1. 强制打源刷新基础数据（收盘后盘中轮询已停）
    from money_flow.market import _fetch_and_cache_major_indices, _fetch_and_cache_distribution, _fetch_and_cache_sh_minute, _fetch_and_cache_daily_closes
    from money_flow.fund_flow import _fetch_and_cache_fund_flow
    from money_flow.turnover import _fetch_and_cache_turnover
    from money_flow.margin import _fetch_and_cache_margin
    _fetch_and_cache_major_indices()
    _fetch_and_cache_distribution()
    _fetch_and_cache_sh_minute()
    _fetch_and_cache_fund_flow()
    _fetch_and_cache_turnover()
    _fetch_and_cache_margin()
    _fetch_and_cache_daily_closes()

    # 2. 恐慌/风险指数基于最新底层数据重算后写入快照
    from money_flow.fear_index import get_fear_index
    from money_flow.risk_index import get_risk_index
    snapshot_update(trade_date, 'fear_index', get_fear_index())
    snapshot_update(trade_date, 'risk_index', get_risk_index())
    print(f'[money_flow] 17:00 快照落库完成: {trade_date}')


def check_money_flow_daily_update():
    """每日快照定时检测：由公共秒级调度器每秒调用一次，到点(17:00)触发固化。"""
    global _auto_next_update
    now_dt = datetime.datetime.now()
    if now_dt >= _auto_next_update:
        _auto_next_update = _next_update_time(now_dt)
        threading.Thread(target=_run_daily_update, daemon=True, name='money-flow-daily').start()


def init_money_flow_daily_update():
    """初始化资金流向每日快照定时任务，返回检测函数供公共调度器注册。"""
    global _auto_next_update
    now_dt = datetime.datetime.now()
    _auto_next_update = _next_update_time(now_dt)
    print(f'[money_flow] 每日快照定时任务已初始化（17:00 下次: {_auto_next_update:%Y-%m-%d %H:%M}）')
    return check_money_flow_daily_update


def get_money_flow_daily(date=None):
    """获取指定交易日资金流向快照（历史回看用，最新交易日走实时逻辑）"""
    trade_date = date or _latest_trading_date()
    data = snapshot_get(trade_date)
    if data is not None:
        return {'success': True, 'date': trade_date, 'data': data}
    return {'success': True, 'date': trade_date, 'data': None, 'empty': True}
