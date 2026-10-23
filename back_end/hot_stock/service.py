"""热股榜 — 同花顺热榜数据。

榜单类型：
- 大家都在看（normal，支持 1小时/24小时）
- 快速飙升中（skyrocket，支持 1小时/24小时）
- 新股热度榜（new_stock，固定 24小时）
- 技术交易派（tech，固定 24小时）
- 价值投资派（value，固定 24小时）
- 趋势投资派（trend，固定 24小时）

单一数据源：同花顺热榜公开接口，不做多源兜底，
请求失败直接抛异常（由 cached_singleflight 透传给调用方）。
"""

from common.http import get_json
from common.cache import cached_singleflight

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

# 热榜为分钟级更新，内存缓存 60s
_CACHE_TTL = 60


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
        stocks.append({
            'rank': item.get('order'),
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


def get_hot_stock(period: str = 'hour', list_type: str = 'normal') -> dict:
    """获取同花顺热股榜（客户端触发，60s 内存缓存 + single-flight）。

    list_type: normal/skyrocket/new_stock/tech/value/trend
    period: hour/day，仅 normal 与 skyrocket 生效，其余固定 day
    """
    if list_type not in _LIST_TYPES:
        return {'success': False, 'error': f'未知榜单类型: {list_type}'}
    if period not in _PERIODS:
        return {'success': False, 'error': f'未知榜单周期: {period}'}

    # 非小时榜类型固定 24 小时
    if list_type not in _HOURLY_TYPES:
        period = 'day'

    if list_type == 'new_stock':
        stocks = cached_singleflight(
            'hot-stock-new_stock', _fetch_new_stock_raw, ttl=_CACHE_TTL)
    else:
        stocks = cached_singleflight(
            f'hot-stock-{list_type}-{period}',
            lambda: _fetch_stock_raw(period, list_type),
            ttl=_CACHE_TTL)

    return {
        'success': True,
        'list_type': list_type,
        'period': period,
        'stocks': stocks,
    }
