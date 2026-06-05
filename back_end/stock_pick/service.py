"""股票搜索 & 行情查询"""
import requests
from common import REQUEST_PROXIES
from common.utils import is_etf


def search_stock(keyword):
    """搜索股票名称或代码"""
    if not keyword or len(keyword.strip()) < 1:
        return {'success': False, 'data': []}

    try:
        url = "https://searchapi.eastmoney.com/api/suggest/get"
        params = {
            'input': keyword.strip(),
            'type': 14,
            'token': 'D43BF722C8E33BDC906FB84D85E326E8',
            'count': 8,
        }
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://www.eastmoney.com/',
        }
        r = requests.get(url, params=params, headers=headers, timeout=8, proxies=REQUEST_PROXIES)
        data = r.json()
        quotes = (data.get('QuotationCodeTable') or {}).get('Data') or []

        KNOWN_MARKETS = {'0', '1', '2', '3', '90', '106', '116'}
        result = []
        secids = []
        for q in quotes:
            code = q.get('Code', '')
            name = q.get('Name', '')
            market = str(q.get('MktNum', ''))
            if code and name and market in KNOWN_MARKETS:
                secid = f"{market}.{code}"
                secids.append(secid)
                result.append({'code': code, 'name': name, 'market': market, 'secid': secid})

        if secids:
            quotes_data = _fetch_quotes(secids)
            for item in result:
                item.update(quotes_data.get(item['secid'], {}))

        return {'success': True, 'data': result}
    except Exception as e:
        return {'success': False, 'error': str(e), 'data': []}


def _fetch_quotes(secids):
    """批量获取股票实时行情"""
    try:
        url = "https://push2delay.eastmoney.com/api/qt/ulist.np/get"
        params = {
            'fltt': 2, 'invt': 2,
            'fields': 'f2,f3,f4,f12,f13',
            'secids': ','.join(secids),
            'ut': 'bd1d9ddb04089700cf9c27f6f7426281',
        }
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://data.eastmoney.com/',
        }
        r = requests.get(url, params=params, headers=headers, timeout=8, proxies=REQUEST_PROXIES)
        diff = (r.json().get('data') or {}).get('diff') or []
        result = {}
        for row in diff:
            key = f"{row.get('f13', '')}.{row.get('f12', '')}"
            price = row.get('f2')
            pct = row.get('f3')
            change = row.get('f4')
            if row.get('f12'):
                etf = is_etf(row.get('f12'), row.get('f13'))
                decimals = 3 if etf else 2
                result[key] = {
                    'price': f"{float(price):.{decimals}f}" if price else '-',
                    'pct': f"{float(pct):.2f}%" if pct is not None else '-',
                    'change': f"{float(change):.{decimals}f}" if change is not None else '-',
                }
        return result
    except Exception:
        return {}
