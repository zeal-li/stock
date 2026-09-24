"""股票搜索 & 行情查询"""
from common.http import get_json, get_realtime_quotes, HEADERS_EM_QUOTE
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
        data = get_json(url, params=params, headers=HEADERS_EM_QUOTE, timeout=8)

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
    """批量获取股票实时行情（走 common.http.get_realtime_quotes，返回字段固定为 price/pct/change 等）"""
    try:
        quotes = get_realtime_quotes(','.join(secids))
        result = {}
        for key, q in quotes.items():
            etf = is_etf(q['code'], q['market'])
            decimals = 3 if etf else 2
            result[key] = {
                'price': f"{q['price']:.{decimals}f}" if q['price'] is not None else '-',
                'pct': f"{q['pct']:.2f}%" if q['pct'] is not None else '-',
                'change': f"{q['change']:.{decimals}f}" if q['change'] is not None else '-',
            }
        return result
    except Exception:
        return {}
