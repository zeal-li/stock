import requests, os
os.environ['no_proxy'] = '*'
p = {'http': None, 'https': None}
h = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://data.eastmoney.com/rzrq/'}

# 东财 rzrq 页面实际调用的 API - 从页面 JS 推测
# 融资融券汇总数据 API
try:
    r = requests.get('https://push2delay.eastmoney.com/api/qt/stock/get',
        params={'secid': '90.BK0597', 'fields': 'f43,f44,f45,f46,f57,f58,f170,f171,f172',
                'ut': 'b2884a393a59ad64002292a3e90d46a5'},
        headers=h, timeout=10, proxies=p)
    print(f'BK0597 (融资融券板块): {r.text[:400]}')
except Exception as e:
    print(f'BK0597: {e}')
print('---')

# 试试取每日 K线 for 1.000001
try:
    r2 = requests.get('https://push2delay.eastmoney.com/api/qt/stock/kline/get',
        params={'secid': '1.000001', 'klt': '101', 'lmt': '10',
                'fields1': 'f1,f2,f3,f4,f5,f6',
                'fields2': 'f51,f52,f53,f54,f55,f56,f57',
                'ut': 'fa5fd1943c7b386f172d6893dbfba10b'},
        headers=h, timeout=10, proxies=p)
    d2 = r2.json()
    kl = (d2.get('data') or {}).get('klines') or []
    print(f'Kline 1.000001: {len(kl)} lines')
    for k in kl[:2]:
        print(f'  {k}')
except Exception as e:
    print(f'Kline: {e}')
