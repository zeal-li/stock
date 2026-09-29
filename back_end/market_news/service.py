"""市场资讯 - 东方财富全球财经资讯（single-flight 缓存）"""
import akshare as ak

from common.cache import cached_singleflight

_CACHE_KEY = 'market-news:global'
_CACHE_TTL = 1800  # 30 分钟


def _load_global_news():
    """真正访问数据源：东方财富全球财经资讯。失败抛异常（不缓存）。"""
    df = ak.stock_info_global_em()
    if df is None or df.empty:
        raise RuntimeError('未获取到数据')

    result = []
    for _, row in df.iterrows():
        result.append({
            'title': str(row.get('标题', '')),
            'summary': str(row.get('摘要', '')),
            'time': str(row.get('发布时间', '')),
            'url': str(row.get('链接', '')),
        })
    return {'success': True, 'data': result}


def get_hot_list():
    """获取东方财富全球财经资讯（缓存 30 分钟，single-flight 防并发击穿）"""
    try:
        return cached_singleflight(_CACHE_KEY, _load_global_news, ttl=_CACHE_TTL)
    except Exception as e:
        return {'success': False, 'error': str(e)}
