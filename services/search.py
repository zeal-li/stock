"""股票搜索"""
import requests
from . import REQUEST_PROXIES


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

        result = []
        for q in quotes:
            code = q.get('Code', '')
            name = q.get('Name', '')
            market = q.get('MktNum', '')
            if code and name:
                result.append({
                    'code': code, 'name': name, 'market': market,
                    'secid': f"{market}.{code}" if market else code,
                })
        return {'success': True, 'data': result}
    except Exception as e:
        return {'success': False, 'error': str(e), 'data': []}
