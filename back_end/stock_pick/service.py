"""股票搜索 & 行情查询"""
import requests
from common import REQUEST_PROXIES
from common.utils import is_etf


def search_stock(keyword):
    """搜索股票名称或代码，使用东方财富 codetable 搜索接口"""
    if not keyword or len(keyword.strip()) < 1:
        return {'success': False, 'data': []}

    try:
        kw = keyword.strip()
        url = "https://search-codetable.eastmoney.com/codetable/search/web"
        params = {
            'client': 'web',
            'clientType': 'webSuggest',
            'clientVersion': 'lastest',
            'keyword': kw,
            'pageIndex': 1,
            'pageSize': 10,
        }
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://quote.eastmoney.com/',
        }
        r = requests.get(url, params=params, headers=headers, timeout=8, proxies=REQUEST_PROXIES)
        data = r.json()

        items = data.get('result') or []
        # 过滤：只保留深A/沪A/基金（含ETF），排除债券/指数/港股/英股等
        VALID_TYPES = {'深A', '沪A', '基金'}
        VALID_MARKETS = {'0', '1'}  # 只保留深市(0)和沪市(1)
        result = []
        secids = []
        seen = set()
        for item in items:
            code = item.get('code', '')
            name = item.get('shortName', '')
            market = str(item.get('market', ''))
            sec_type = item.get('securityTypeName', '')
            if not code or not name or sec_type not in VALID_TYPES or market not in VALID_MARKETS:
                continue
            key = f"{market}.{code}"
            if key in seen:
                continue
            seen.add(key)
            secid = f"{market}.{code}"
            secids.append(secid)
            result.append({'code': code, 'name': name, 'market': market, 'secid': secid})
            if len(result) >= 8:
                break

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
