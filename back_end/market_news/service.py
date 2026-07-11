"""市场资讯 - 东方财富全球财经资讯"""
import akshare as ak


def get_hot_list():
    """获取东方财富全球财经资讯（最新200条）"""
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

        return {'success': True, 'data': result}

    except Exception as e:
        return {'success': False, 'error': str(e)}
