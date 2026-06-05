"""资金流向：成交额分时"""
from .market_data import _cache, _TURNOVER_MINUTE_KEY


def get_index_minute_data():
    """成交额分时数据（数据由后台轮询线程每分钟更新，此处仅读缓存）"""
    cached = _cache.get(_TURNOVER_MINUTE_KEY)
    if cached:
        return cached[0]
    return {'success': False, 'error': '暂无成交额数据'}
