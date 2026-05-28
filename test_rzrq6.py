import requests, os
os.environ['no_proxy'] = '*'
p = {'http': None, 'https': None}
h = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://data.eastmoney.com/'}

reports = [
    "RPT_DAILY_MARGIN_DETAILS",
    "RPT_MARGIN_TRADING",
    "RPTA_MARGIN_TOTAL",
    "RPTA_WEB_MARGIN",
    "RPT_WEB_MARGIN",
    "RPT_MARGIN_SUMMARY",
]

for rpt in reports:
    url = f"https://datacenter-web.eastmoney.com/api/data/v1/get?reportName={rpt}&columns=ALL&pageSize=3&pageNumber=1&sortColumns=TRADE_DATE&sortTypes=-1"
    try:
        r = requests.get(url, headers=h, timeout=10, proxies=p)
        d = r.json()
        if d.get('success'):
            print(f'{rpt}: SUCCESS!')
            print(f'  keys: {list(d.keys())}')
            result = d.get('result', {})
            print(f'  result keys: {list(result.keys()) if isinstance(result, dict) else str(result)[:200]}')
            break
        else:
            print(f'{rpt}: {d.get("message","")}')
    except Exception as e:
        print(f'{rpt}: {e}')
    print('---')
