"""连板榜 — 东方财富涨停池数据（按连板数降序）。

单一数据源：东方财富涨停池接口 getTopicZTPool。
涨停池包含当日所有涨停股（含首板与连板），按连板数(lbc)降序返回。

取数规则：
- 今天（最新交易日）：未开盘直接返回空；盘中先查库，库里没有或落库超 10 分钟
  重新请求东财并落库；落库时间已过收盘(15:00)则直接返回，不再请求东财。
- 历史日期：先查库，命中直接返回；未命中时，若早于最新交易日 7 天直接返回空，
  7 天内请求东财，有数据落库返回，空数据不落库。
- 并发请求经 cached_singleflight 合并，只向东财请求一次。
- 交易日 17:00 定时抓取落库 + 清理过期数据。
"""
import datetime
import time

from common.http import get_json, HEADERS_EM_DATA
from common.cache import cached_singleflight
from common.utils import is_a_share_trading_day, is_market_opened, to_minutes
from lianban_bang.storage import rank_get, rank_set, cleanup_old_data

_ZT_POOL_URL = 'https://push2ex.eastmoney.com/getTopicZTPool'
_EM_ZT_UT = '7eea3edcaed734bea9cbfc24409ed989'

# 盘中刷新阈值：落库时间超过该秒数则重新请求东财
_REFRESH_SECONDS = 10 * 60
# 历史数据可回查窗口：早于最新交易日该天数，直接返回空，不请求东财
_HISTORY_WINDOW_DAYS = 7
# A股收盘时间（时, 分）
_CLOSE_TIME = (15, 0)


def _target_trade_day():
    """最新有效交易日：盘中(>=09:30)取当日；盘前/非交易日取最近已收盘交易日"""
    now = datetime.datetime.now()
    d = now.date()
    while not is_a_share_trading_day(d):
        d -= datetime.timedelta(days=1)
    if d == now.date() and now.hour * 60 + now.minute < 9 * 60 + 30:
        d -= datetime.timedelta(days=1)
        while not is_a_share_trading_day(d):
            d -= datetime.timedelta(days=1)
    return d


def _fmt_time(v):
    """封板时间 92500 → '09:25'"""
    if v is None:
        return ''
    s = str(int(v)).zfill(6)
    return s[:2] + ':' + s[2:4]


def _fetch_lianban(day_str):
    """请求东财涨停池并规整，返回按连板数降序的列表（无数据返回空列表）"""
    params = {
        'ut': _EM_ZT_UT, 'dpt': 'wz.ztzt',
        'Pageindex': '0', 'pagesize': '6000',
        'sort': 'fbt:asc', 'date': day_str,
    }
    body = get_json(_ZT_POOL_URL, params=params, headers=HEADERS_EM_DATA, timeout=10)
    data = body.get('data')
    if data is None:
        return []
    pool = data.get('pool') or []

    rows = []
    for x in pool:
        code = str(x.get('c') or '')
        if not code:
            continue
        zttj = x.get('zttj') or {}
        rows.append({
            'code': code,
            'market': str(x.get('m') if x.get('m') is not None else ''),
            'name': str(x.get('n') or ''),
            'price': round(x.get('p') / 1000, 2) if x.get('p') is not None else None,
            'change_pct': x.get('zdp'),
            'amount': x.get('amount'),
            'float_cap': x.get('ltsz'),
            'turnover': x.get('hs'),
            'lbc': int(x.get('lbc') or 1),
            'fbt': _fmt_time(x.get('fbt')),
            'lbt': _fmt_time(x.get('lbt')),
            'zbc': int(x.get('zbc') or 0),
            'fund': x.get('fund'),
            'industry': str(x.get('hybk') or ''),
            'zttj_days': zttj.get('days'),
            'zttj_ct': zttj.get('ct'),
        })

    rows.sort(key=lambda r: -r['lbc'])
    return rows


def _fetch_and_save(date_str):
    """请求东财并落库（经 singleflight 合并并发）。返回列表（可能为空，空不落库）。"""
    def loader():
        day_str = date_str.replace('-', '')
        rows = _fetch_lianban(day_str)
        if rows:
            rank_set(date_str, rows)
        return rows

    return cached_singleflight(f'lianban-bang-fetch-{date_str}', loader, ttl=0)


def _is_after_close(ts):
    """落库时间戳是否已过 A 股收盘(15:00)"""
    dt = datetime.datetime.fromtimestamp(ts)
    return to_minutes(dt.hour, dt.minute) >= to_minutes(*_CLOSE_TIME)


def get_lianban(date=None):
    """获取连板榜数据。date: 'YYYY-MM-DD' 或 None（None 时取最新交易日）。"""
    now = datetime.datetime.now()
    today = now.date()
    latest = _target_trade_day()

    if not date:
        date = latest.strftime('%Y-%m-%d')

    d = datetime.datetime.strptime(date, '%Y-%m-%d').date()
    is_today = (d == today)

    # ============ 今天（最新交易日候选）============
    if is_today:
        # 未开盘（盘前或今天非交易日）：直接返回空，不请求东财
        if not is_market_opened('0'):
            return {'success': True, 'date': date, 'list': [], 'empty': True}
        cached = rank_get(date)
        if cached:
            data, updated_at = cached
            # 落库时间已过收盘：数据不再变更，直接返回
            if _is_after_close(updated_at):
                return {'success': True, 'date': date, 'list': data}
            # 落库未超 10 分钟：直接返回
            if time.time() - updated_at < _REFRESH_SECONDS:
                return {'success': True, 'date': date, 'list': data}
        # 库里没有，或已超 10 分钟：重新请求并落库
        data = _fetch_and_save(date)
        return {'success': True, 'date': date, 'list': data}

    # ============ 历史日期（非今天）============
    cached = rank_get(date)
    if cached:
        return {'success': True, 'date': date, 'list': cached[0]}

    # 库里没有：早于最新交易日 7 天 → 直接返回空，不请求东财
    if (latest - d).days > _HISTORY_WINDOW_DAYS:
        return {'success': True, 'date': date, 'list': [], 'empty': True}

    # 7 天内：请求东财（空数据不落库）
    data = _fetch_and_save(date)
    if data:
        return {'success': True, 'date': date, 'list': data}
    return {'success': True, 'date': date, 'list': [], 'empty': True}


# =========== 每日 17:00 定时任务：先清理旧数据，再抓取当日连板榜落库 ===========
# 17:00 触发时：先清理过期数据（每天执行），再抓取当日涨停池落库（仅交易日执行）。
# 复用 _fetch_lianban 单一数据源链路，不另开数据源。

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


def _run_auto_update():
    """每日 17:00 抓取当日连板榜落库。非交易日直接跳过。"""
    today = datetime.date.today()
    if not is_a_share_trading_day(today):
        print(f'[lianban_bang] 17:00 自动落库跳过: {today} 非A股交易日')
        return
    today_str = today.strftime('%Y-%m-%d')
    rows = _fetch_lianban(today_str.replace('-', ''))
    done_at = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    if rows:
        rank_set(today_str, rows)
        print(f'[lianban_bang] 17:00 落库完成: {today_str}，{len(rows)} 只（执行时间 {done_at}）')
    else:
        print(f'[lianban_bang] 17:00 无数据，不落库: {today_str}（执行时间 {done_at}）')


def check_lianban_bang_update():
    """连板榜定时检测：由公共秒级调度器每秒调用一次，每日 17:00 触发清理 + 落库。"""
    global _auto_next_update
    now = datetime.datetime.now()
    if now >= _auto_next_update:
        _auto_next_update = _next_update_time(now)
        cleanup_old_data()
        _run_auto_update()


def init_lianban_bang_update():
    """初始化 17:00 定时任务，返回检测函数供公共调度器注册（由 app.py 启动时调用）。"""
    global _auto_next_update
    now = datetime.datetime.now()
    _auto_next_update = _next_update_time(now)
    print(f'[lianban_bang] 定时任务已初始化（17:00 自动落库下次: {_auto_next_update:%Y-%m-%d %H:%M}）')
    return check_lianban_bang_update
