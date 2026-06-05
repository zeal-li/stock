"""财务数据（商誉率/质押率等）"""
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from . import REQUEST_PROXIES

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Referer': 'https://emweb.securities.eastmoney.com/',
}
PLEDGE_HEADERS = {
    'User-Agent': HEADERS['User-Agent'],
    'Referer': 'https://data.eastmoney.com/',
}


def _get_goodwill_rate(code):
    """获取单只股票最新商誉率（商誉/净资产 %），失败返回 None"""
    prefix = 'SH' if code.startswith(('6', '9')) else 'SZ'
    symbol = f"{prefix}{code}"
    try:
        r = requests.get(
            "https://emweb.securities.eastmoney.com/PC_HSF10/NewFinanceAnalysis/zcfzbDateAjaxNew",
            params={"companyType": "4", "reportDateType": "0", "code": symbol},
            headers=HEADERS, timeout=10, proxies=REQUEST_PROXIES,
        )
        dates = (r.json().get('data') or [])
        if not dates:
            return None
        latest_date = dates[0]['REPORT_DATE'].split(' ')[0]

        r = requests.get(
            "https://emweb.securities.eastmoney.com/PC_HSF10/NewFinanceAnalysis/zcfzbAjaxNew",
            params={"companyType": "4", "reportDateType": "0", "reportType": "1",
                    "dates": latest_date, "code": symbol},
            headers=HEADERS, timeout=10, proxies=REQUEST_PROXIES,
        )
        rows = (r.json().get('data') or [])
        if not rows:
            return None
        row = rows[0]
        goodwill = float(row.get('GOODWILL') or 0)
        total_equity = float(row.get('TOTAL_EQUITY') or 0)
        if total_equity:
            return round(goodwill / total_equity * 100, 2)
        return None
    except Exception:
        return None


def _get_pledge_rates(codes):
    """批量获取质押率，一次请求查全部股票"""
    if not codes:
        return {}
    try:
        code_list = ','.join(f'"{c}"' for c in codes)
        r = requests.get(
            "https://datacenter-web.eastmoney.com/api/data/v1/get",
            params={
                "reportName": "RPT_CSDC_LIST",
                "columns": "SECURITY_CODE,PLEDGE_RATIO",
                "filter": f'(SECURITY_CODE in ({code_list}))',
                "pageSize": len(codes),
                "sortColumns": "TRADE_DATE",
                "sortTypes": "-1",
            },
            headers=PLEDGE_HEADERS, timeout=10, proxies=REQUEST_PROXIES,
        )
        data = r.json()
        rows = (data.get('result') or {}).get('data') or []
        result = {}
        for row in rows:
            code = row.get('SECURITY_CODE', '')
            rate = row.get('PLEDGE_RATIO')
            if code and rate is not None:
                result[code] = round(float(rate), 2)
        return result
    except Exception:
        return {}


def get_goodwill(codes):
    """批量获取商誉率+质押率：商誉逐股并行，质押批量一次查"""
    if not codes:
        return {}

    gw_map = {}
    with ThreadPoolExecutor(max_workers=min(len(codes), 10)) as pool:
        futures = {pool.submit(_get_goodwill_rate, c): c for c in codes}
        for future in as_completed(futures):
            code = futures[future]
            try:
                gw_map[code] = future.result()
            except Exception:
                gw_map[code] = None

    pl_map = _get_pledge_rates(codes)

    result = {}
    for code in codes:
        result[code] = {
            'gw': gw_map.get(code),
            'pld': pl_map.get(code),
        }
    return result
