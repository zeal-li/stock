"""全球指数实时行情 - A股指数（东方财富 push2delay）"""

import requests
from common import REQUEST_PROXIES

_EM_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Referer': 'https://data.eastmoney.com/',
}
_EM_UT = 'bd1d9ddb04089700cf9c27f6f7426281'

# A股主要指数：名称, 代码, 市场(1=上海, 0=深圳)
A_INDEX_LIST = [
    ('上证指数', '000001', '1'),
    ('深证成指', '399001', '0'),
    ('创业板指', '399006', '0'),
    ('科创50',   '000688', '1'),
    ('沪深300',  '000300', '1'),
    ('中证500',  '000905', '1'),
    ('中证1000', '000852', '1'),
    ('北证50',   '899050', '0'),
    ('上证50',   '000016', '1'),
]


def get_global_indices():
    """全球指数实时行情（当前：A股指数）"""
    try:
        secids = ','.join(f"{m}.{c}" for _, c, m in A_INDEX_LIST)
        url = "https://push2delay.eastmoney.com/api/qt/ulist.np/get"
        params = {
            'fltt': 2, 'invt': 2,
            'fields': 'f2,f3,f4,f12,f14',
            'secids': secids,
            'ut': _EM_UT,
        }
        r = requests.get(url, params=params, headers=_EM_HEADERS, timeout=8, proxies=REQUEST_PROXIES)
        diff = (r.json().get('data') or {}).get('diff') or []

        # 按 secids 参数顺序排列结果
        ordered = {row.get('f12', ''): row for row in diff}
        data = []
        for name, code, market in A_INDEX_LIST:
            row = ordered.get(code)
            if not row:
                continue
            price = row.get('f2')
            change_pct = row.get('f3')
            change_val = row.get('f4')
            data.append({
                'name': name,
                'code': code,
                'price': f"{float(price):.2f}" if price is not None else '-',
                'change': f"{'+' if change_pct and float(change_pct) >= 0 else ''}{float(change_pct):.2f}%" if change_pct is not None else '-',
                'change_value': f"{'+' if change_val and float(change_val) >= 0 else ''}{float(change_val):.2f}" if change_val is not None else '-',
            })

        if data:
            return {'success': True, 'data': data}
        return {'success': False, 'error': '暂无指数数据'}
    except Exception as e:
        return {'success': False, 'error': str(e)}
