"""热股榜 — 同花顺热榜数据（按自然日持久化 + 落库时间刷新判断）。

榜单类型：
- 大家都在看（normal，支持 1小时/24小时）
- 快速飙升中（skyrocket，支持 1小时/24小时）
- 新股热度榜（new_stock，固定 24小时）
- 技术交易派（tech，固定 24小时）
- 价值投资派（value，固定 24小时）
- 趋势投资派（trend，固定 24小时）

取数规则（单一数据源，不做多源兜底）：
- 客户端先查库；非最新自然日无数据直接返回 empty，不再请求同花顺。
- 最新自然日（今天）：无数据先请求同花顺并落库；
  落库时间超过 1 小时则重新请求同花顺刷新（不区分 1小时/24小时口径）；
  并发请求经 cached_singleflight 合并，只向同花顺请求一次。
- 每天 23:30 定时落库当天所有榜单组合。
"""

import datetime
import threading
import time

from common.http import get_json
from common.cache import cached_singleflight
from hot_stock.storage import rank_get, rank_set, cleanup_old_data

# 普通热榜（大家在看的 / 快速飙升 / 三个投资流派）
_STOCK_API = 'https://dq.10jqka.com.cn/fuyao/hot_list_data/out/hot_list/v1/stock'
# 新股热度榜（独立接口）
_NEW_STOCK_API = 'https://eq.10jqka.com.cn/open/api/hot_list/rank/v1/new_stock.txt'

_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://eq.10jqka.com.cn/',
}

_PERIODS = {'hour': '1小时', 'day': '24小时'}
_LIST_TYPES = {
    'normal': '大家都在看',
    'skyrocket': '快速飙升中',
    'new_stock': '新股热度榜',
    'tech': '技术交易派',
    'value': '价值投资派',
    'trend': '趋势投资派',
}
# 支持 1小时/24小时 切换的榜单，其余固定 24 小时
_HOURLY_TYPES = {'normal', 'skyrocket'}

# 每天 23:30 定时落库的所有榜单组合
_ALL_COMBINATIONS = [
    ('normal', 'hour'), ('normal', 'day'),
    ('skyrocket', 'hour'), ('skyrocket', 'day'),
    ('new_stock', 'day'),
    ('tech', 'day'), ('value', 'day'), ('trend', 'day'),
]

# 统一刷新阈值：落库时间超过该秒数则重新请求同花顺刷新（不区分 1小时/24小时）
_REFRESH_SECONDS = 3600

# 每日 23:30 落库任务
_AUTO_UPDATE_TIME = (23, 30)

# 个股异动解读（同花顺 thsHotDetail 页同源接口，按日期返回该股最近的异动解读列表）
_ANOMALY_HISTORY_API = 'https://dq.10jqka.com.cn/fuyao/transaction_history/service/v1/get/{ths_market}_{code}.txt'
# 前端市场标识（0深/1沪/2北）→ 同花顺市场代码
_THS_MARKET_MAP = {'0': '33', '1': '17', '2': '151'}


def _to_int(val):
    """热度值转 int（接口返回字符串，如 '702464.0'）"""
    try:
        return int(float(val))
    except (TypeError, ValueError):
        return 0


def _parse_tag(tag):
    """解析 tag 对象，返回 (popularity_tag, concept_tags)"""
    tag = tag or {}
    return tag.get('popularity_tag') or '', tag.get('concept_tag') or []


def _fetch_stock_raw(period: str, list_type: str) -> list:
    """请求普通热榜接口，解析为前端展示字段列表"""
    data = get_json(_STOCK_API, params={
        'stock_type': 'a',
        'type': period,
        'list_type': list_type,
    }, headers=_HEADERS, timeout=10)

    if not isinstance(data, dict) or data.get('status_code') != 0:
        raise ValueError(f'同花顺热榜接口返回异常: {data}')

    stock_list = (data.get('data') or {}).get('stock_list') or []
    stocks = []
    for item in stock_list:
        popularity_tag, concept_tags = _parse_tag(item.get('tag'))
        # 榜单内排名：流派榜（tech/value/trend）用 display_order，order 是其在全市场总榜的排名
        rank = item.get('display_order') if item.get('display_order') is not None else item.get('order')
        stocks.append({
            'rank': rank,
            'code': item.get('code', ''),
            'name': item.get('name', ''),
            'heat': _to_int(item.get('rate')),
            'change_pct': item.get('rise_and_fall'),
            'popularity_tag': popularity_tag,
            'concept_tags': concept_tags,
            'analyse_title': item.get('analyse_title') or '',
            'analyse': item.get('analyse') or '',
        })
    return stocks


def _fetch_new_stock_raw() -> list:
    """请求新股热度榜接口（字段与普通榜不同：无涨跌幅，含 PE / 上市日期）"""
    data = get_json(_NEW_STOCK_API, headers=_HEADERS, timeout=10)

    if not isinstance(data, dict) or data.get('status_code') != 0:
        raise ValueError(f'同花顺新股热度榜接口返回异常: {data}')

    stock_list = (data.get('data') or {}).get('stock_list') or []
    stocks = []
    for item in stock_list:
        popularity_tag, concept_tags = _parse_tag(item.get('tag'))
        stocks.append({
            'rank': item.get('order'),
            'code': item.get('code', ''),
            'name': item.get('name', ''),
            'heat': _to_int(item.get('rate')),
            'pe': item.get('pe'),
            'order_date': item.get('orderDate', ''),
            'popularity_tag': popularity_tag,
            'concept_tags': concept_tags,
        })
    return stocks


def _fetch_and_save(list_type: str, period: str, date: str) -> list:
    """请求同花顺并落库。经 cached_singleflight(ttl=0) 合并并发：同一时刻多个客户端只请求一次源。

    ttl=0 表示不做 TTL 缓存，仅做 single-flight 并发合并；落库时间的刷新判断在调用方完成。
    """
    def loader():
        stocks = (_fetch_new_stock_raw() if list_type == 'new_stock'
                  else _fetch_stock_raw(period, list_type))
        rank_set(date, list_type, period, stocks)
        return stocks

    return cached_singleflight(f'hot-stock-fetch-{list_type}-{period}', loader, ttl=0)


def get_hot_stock(period: str = 'hour', list_type: str = 'normal', date: str = None) -> dict:
    """获取热股榜（客户端触发）。

    - 非最新自然日：仅读库，无数据返回 empty，不请求同花顺。
    - 最新自然日（今天）：无数据先请求落库；落库超 1 小时重新请求刷新（不区分 1小时/24小时）。
    """
    if list_type not in _LIST_TYPES:
        return {'success': False, 'error': f'未知榜单类型: {list_type}'}
    if period not in _PERIODS:
        return {'success': False, 'error': f'未知榜单周期: {period}'}

    # 非小时榜类型固定 24 小时
    if list_type not in _HOURLY_TYPES:
        period = 'day'

    today = datetime.date.today().strftime('%Y-%m-%d')
    date = date or today

    cached = rank_get(date, list_type, period)

    if date != today:
        if cached:
            data, _ = cached
            return {'success': True, 'date': date, 'list_type': list_type, 'period': period, 'stocks': data}
        return {'success': True, 'date': date, 'list_type': list_type, 'period': period, 'stocks': [], 'empty': True}

    # 最新自然日（今天）
    if cached:
        data, updated_at = cached
        # 统一：落库时间未超 1 小时直接返回缓存；否则往下重新请求同花顺刷新
        if time.time() - updated_at < _REFRESH_SECONDS:
            return {'success': True, 'date': date, 'list_type': list_type, 'period': period, 'stocks': data}

    stocks = _fetch_and_save(list_type, period, today)
    return {'success': True, 'date': today, 'list_type': list_type, 'period': period, 'stocks': stocks}


def get_stock_anomaly(code: str, market: str) -> dict:
    """个股异动解读列表（同花顺，按日期倒序，最多最近几天）。

    market 为前端市场标识（0深/1沪/2北）。返回 items:
    [{date, tag(涨停/大跌等), title(关键词拼接), reason(解读正文)}]；
    该股无异动记录返回空列表。

    后端不做缓存，每次请求直接打同花顺；缓存由前端 localStorage（1 小时有效）负责。
    """
    code = (code or '').strip()
    ths_market = _THS_MARKET_MAP.get(str(market or '').strip())
    if not code or not ths_market:
        return {'success': False, 'error': '缺少股票代码或市场参数'}

    url = _ANOMALY_HISTORY_API.format(ths_market=ths_market, code=code)

    try:
        data = get_json(url, headers=_HEADERS, timeout=10)
    except Exception as e:
        return {'success': False, 'error': str(e)}

    if not isinstance(data, dict) or data.get('status_code') != 0:
        return {'success': False, 'error': f'同花顺异动解读接口返回异常: {data}'}

    lst = (data.get('data') or {}).get('anomalyAnalysisList') or []
    items = [
        {
            'date': it.get('date') or '',
            'tag': it.get('tagName') or '',
            'title': '+'.join(it.get('keywordList') or []),
            'reason': it.get('reason') or '',
        }
        for it in lst
    ]
    return {'success': True, 'code': code, 'items': items}


# =========== 定时任务：每日 23:30 落库 ===========

_auto_next_update = None   # 下一次 23:30 任务时刻


def _next_update_time(base):
    """返回 base 当天 23:30；若已过则返回次日 23:30"""
    cand = base.replace(hour=_AUTO_UPDATE_TIME[0], minute=_AUTO_UPDATE_TIME[1],
                        second=0, microsecond=0)
    if cand <= base:
        cand = (base + datetime.timedelta(days=1)).replace(
            hour=_AUTO_UPDATE_TIME[0], minute=_AUTO_UPDATE_TIME[1],
            second=0, microsecond=0)
    return cand


def _run_daily_update():
    """每日 23:30 任务：清理过期数据，并全量落库当天所有榜单组合。

    绕过 single-flight 缓存，直接打源落库（覆盖当天盘中/请求时的快照为收盘数据）。
    """
    cleanup_old_data()

    today = datetime.date.today().strftime('%Y-%m-%d')
    for list_type, period in _ALL_COMBINATIONS:
        try:
            stocks = (_fetch_new_stock_raw() if list_type == 'new_stock'
                      else _fetch_stock_raw(period, list_type))
            rank_set(today, list_type, period, stocks)
        except Exception as e:
            print(f'[hot_stock] 23:30 落库失败 {list_type}/{period}: {e}')
    print(f'[hot_stock] 23:30 落库完成: {today}')


def check_hot_stock_update():
    """热股榜定时检测：由公共秒级调度器每秒调用一次，每日 23:30 触发落库。

    落库任务耗时较长（要抓取全部 8 个榜单组合），放到独立线程执行，避免阻塞调度器。
    """
    global _auto_next_update
    now_dt = datetime.datetime.now()
    if now_dt >= _auto_next_update:
        _auto_next_update = _next_update_time(now_dt)
        threading.Thread(target=_run_daily_update, daemon=True, name='hot-stock-daily').start()


def init_hot_stock_update():
    """初始化热股榜定时任务，返回检测函数供公共调度器注册（由 app.py 启动时调用）。"""
    global _auto_next_update
    now_dt = datetime.datetime.now()
    _auto_next_update = _next_update_time(now_dt)
    print(f'[hot_stock] 定时任务已初始化（23:30 落库下次: {_auto_next_update:%Y-%m-%d %H:%M}）')
    return check_hot_stock_update
