import requests, os
os.environ['no_proxy'] = '*'
p = {'http': None, 'https': None}
h = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://data.eastmoney.com/'}

tests = [
    ("datacenter RZRQ", "https://datacenter-web.eastmoney.com/api/data/v1/get?reportName=RPT_MARGIN_TRADEINFO&columns=ALL&sortColumns=TRADE_DATE&sortTypes=-1&pageSize=5&pageNumber=1"),
    ("datacenter RZRQ v2", "https://datacenter-web.eastmoney.com/api/data/v1/get?reportName=RPT_DAILY_BILLBOARD&columns=ALL&pageSize=5&pageNumber=1"),
    ("rzrq page HTML", "https://data.eastmoney.com/rzrq/total"),
    ("rzrq kline try", "https://push2delay.eastmoney.com/api/qt/stock/kline/get?secid=1.000001&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52&klt=101&lmt=10&ut=b2884a393a59ad64002292a3e90d46a5"),
]

for name, url in tests:
    try:
        r = requests.get(url, headers=h, timeout=10, proxies=p)
        print(f'{name}: status={r.status_code}, len={len(r.text)}')
        if 'application/json' in r.headers.get('content-type',''):
            d = r.json()
            print(f'  {str(d)[:400]}')
        else:
            print(f'  {r.text[:200]}')
    except Exception as e:
        print(f'{name}: {e}')
    print('---')
