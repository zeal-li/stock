import requests, os
os.environ['no_proxy'] = '*'
p = {'http': None, 'https': None}
h = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://data.eastmoney.com/'}

# push2his 历史 K线
url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
params = {'secid': '1.000001', 'klt': '101', 'lmt': '10',
          'fields1': 'f1,f2,f3,f4,f5,f6',
          'fields2': 'f51,f52,f53,f54,f55,f56,f57',
          'ut': 'fa5fd1943c7b386f172d6893dbfba10b'}
try:
    r = requests.get(url, params=params, headers=h, timeout=10, proxies=p)
    print(f'push2his: {r.status_code}, text: {r.text[:400]}')
except Exception as e:
    print(f'push2his: {e}')

print('---')

# 同花顺 rzrq 页面
try:
    r2 = requests.get('https://data.10jqka.com.cn/rzrq/', headers={**h, 'Referer': 'https://www.10jqka.com.cn/'}, timeout=10, proxies=p)
    print(f'10jqka rzrq: {r2.status_code}, len={len(r2.text)}')
except Exception as e:
    print(f'10jqka: {e}')
