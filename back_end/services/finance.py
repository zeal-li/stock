"""财务数据（商誉率/质押率等）"""
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from . import REQUEST_PROXIES

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Referer': 'https://emweb.securities.eastmoney.com/',
}


def _get_goodwill_rate(code):
    """获取单只股票最新商誉率（商誉/净资产 %）"""
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
            return 0
        latest_date = dates[0]['REPORT_DATE'].split(' ')[0]

        r = requests.get(
            "https://emweb.securities.eastmoney.com/PC_HSF10/NewFinanceAnalysis/zcfzbAjaxNew",
            params={"companyType": "4", "reportDateType": "0", "reportType": "1",
                    "dates": latest_date, "code": symbol},
            headers=HEADERS, timeout=10, proxies=REQUEST_PROXIES,
        )
        rows = (r.json().get('data') or [])
        if not rows:
            return 0
        row = rows[0]
        goodwill = float(row.get('GOODWILL') or 0)
        total_equity = float(row.get('TOTAL_EQUITY') or 0)
        if total_equity:
            return round(goodwill / total_equity * 100, 2)
        return 0
    except Exception:
        return 0


def _get_pledge_rate(code):
    """获取单只股票最新质押比例（%）"""
    try:
        r = requests.get(
            "https://datacenter-web.eastmoney.com/api/data/v1/get",
            params={
                "reportName": "RPT_CSDC_LIST",
                "columns": "PLEDGE_RATIO",
                "filter": f'(SECURITY_CODE="{code}")',
                "pageSize": 1,
                "sortColumns": "TRADE_DATE",
                "sortTypes": "-1",
            },
            headers={'User-Agent': HEADERS['User-Agent'],
                     'Referer': 'https://data.eastmoney.com/'},
            timeout=10, proxies=REQUEST_PROXIES,
        )
        data = r.json()
        rows = (data.get('result') or {}).get('data') or []
        if not rows:
            return 0
        return round(float(rows[0].get('PLEDGE_RATIO', 0)), 2)
    except Exception:
        return 0


def _get_ratios(code):
    """获取单只股票的商誉率和质押率（并行内部两请求）"""
    with ThreadPoolExecutor(max_workers=2) as pool:
        f_gw = pool.submit(_get_goodwill_rate, code)
        f_pl = pool.submit(_get_pledge_rate, code)
        return {
            'gw': f_gw.result(),
            'pld': f_pl.result(),
        }


def get_goodwill(codes):
    """批量获取商誉率+质押率，5线程并行"""
    result = {}
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(_get_ratios, code): code for code in codes}
        for future in as_completed(futures):
            code = futures[future]
            try:
                result[code] = future.result()
            except Exception:
                result[code] = {'gw': 0, 'pld': 0}
    return result
