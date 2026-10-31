"""连板榜 — 东方财富涨停池数据（按连板数降序）。

单一数据源：东方财富涨停池接口 getTopicZTPool。
涨停池包含当日所有涨停股（含首板与连板），本模块按连板数(lbc)降序返回，
连板数最高的排在最前。盘中数据经 cached_singleflight 30 秒缓存 + 并发合并。
"""
import datetime

from common.http import get_json, HEADERS_EM_DATA
from common.cache import cached_singleflight
from common.utils import is_a_share_trading_day

_ZT_POOL_URL = 'https://push2ex.eastmoney.com/getTopicZTPool'
_EM_ZT_UT = '7eea3edcaed734bea9cbfc24409ed989'


def _target_trade_day():
    """连板榜目标交易日：盘中(>=09:30)取当日；盘前/非交易日取最近已收盘交易日"""
    now = datetime.datetime.now()
    d = now.date()
    while not is_a_share_trading_day(d):
        d -= datetime.timedelta(days=1)
    # 盘前（今天尚未开盘）：今日数据未生成，回退到上一交易日
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
    """抓取涨停池并规整，返回按连板数降序的列表"""
    params = {
        'ut': _EM_ZT_UT, 'dpt': 'wz.ztzt',
        'Pageindex': '0', 'pagesize': '6000',
        'sort': 'fbt:asc', 'date': day_str,
    }
    body = get_json(_ZT_POOL_URL, params=params, headers=HEADERS_EM_DATA, timeout=10)
    data = body.get('data')
    if data is None:
        raise RuntimeError(f'涨停池数据为空（东财 {_ZT_POOL_URL}）')
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

    # 连板数最高的排最前
    rows.sort(key=lambda r: -r['lbc'])
    return rows


def get_lianban(date=None):
    """获取连板榜数据。

    date: 'YYYY-MM-DD' 或 None（None 时取最近交易日）。
    经 cached_singleflight(ttl=30) 缓存 + 并发合并：盘中数据 30 秒内共享同一份结果。
    """
    if not date:
        date = _target_trade_day().strftime('%Y-%m-%d')
    day_str = date.replace('-', '')
    rows = cached_singleflight(f'lianban-{day_str}', lambda: _fetch_lianban(day_str), ttl=30)
    return {'success': True, 'date': date, 'list': rows}
