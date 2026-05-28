import requests, os
os.environ['no_proxy'] = '*'
p = {'http': None, 'https': None}
h = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://data.eastmoney.com/'}

# 尝试融资融券数据接口
tests = [
    ("push2 stock fields", "https://push2delay.eastmoney.com/api/qt/stock/get?secid=1.000001&fields=f43,f117,f137,f138,f184,f152,f161,f162,f173,f174&ut=fa5fd1943c7b386f172d6893dbfba10b"),
    ("东方财富数据中心", "https://datacenter-web.eastmoney.com/api/data/v1/get?reportName=RPTA_WEB_RZRQ_SUMMARY&columns=ALL&sortColumns=TRADE_DATE&sortTypes=-1&pageSize=5&pageNumber=1"),
    ("rzrq total", "https://push2delay.eastmoney.com/api/qt/stock/rzrq/kline/get?secid=1.000001&fields1=f1&fields2=f51,f52,f53&klt=101&lmt=30&ut=b2884a393a59ad64002292a3e90d46a5"),
]

for name, url in tests:
    try:
        r = requests.get(url, headers=h, timeout=10, proxies=p)
        print(f'{name}: status={r.status_code}, len={len(r.text)}')
        print(f'  {r.text[:400]}')
    except Exception as e:
        print(f'{name}: {e}')
    print('---')
