"""市场资讯 - 东方财富全球财经资讯（带缓存）"""
import time
import akshare as ak

# 缓存：{data, timestamp}
_cache = None


def get_hot_list():
    """获取东方财富全球财经资讯（缓存30分钟）"""
    global _cache

    now = time.time()
    if _cache is not None and (now - _cache['timestamp']) < 1800:
        return _cache['data']

    try:
        df = ak.stock_info_global_em()
        if df is None or df.empty:
            return {'success': False, 'error': '未获取到数据'}

        result = []
        for _, row in df.iterrows():
            result.append({
                'title': str(row.get('标题', '')),
                'summary': str(row.get('摘要', '')),
                'time': str(row.get('发布时间', '')),
                'url': str(row.get('链接', '')),
            })

        data = {'success': True, 'data': result}
        _cache = {'data': data, 'timestamp': now}
        return data

    except Exception as e:
        return {'success': False, 'error': str(e)}
