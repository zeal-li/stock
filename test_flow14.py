import requests, os, json
os.environ['no_proxy'] = '*'
proxies = {'http': None, 'https': None}
h = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

# 测试 push2 API 带正确 Referer
url = "https://push2.eastmoney.com/api/qt/stock/fflow/kline/get?secid=1.000001&fields1=f1,f2,f3,f7&fields2=f51,f52&klt=1&lmt=3"
h2 = {**h, 'Referer': 'https://data.eastmoney.com/zjlx/'}
try:
    r = requests.get(url, headers=h2, timeout=10, proxies=proxies)
    print(f'push2 fflow: status={r.status_code}, len={len(r.text)}')
    d = r.json()
    kl = d.get('data', {}).get('klines', [])
    print(f'klines: {len(kl)}')
    for k in kl[:3]:
        p = k.split(',')
        print(f'  {p[0]} main_flow={float(p[1])/1e8:.2f}亿')
except Exception as e:
    print(f'push2: {e}')

# 尝试不带场次二的 push2，看是否是 fields2 太长导致
print('\n=== push2 最小参数 ===')
url3 = "https://push2.eastmoney.com/api/qt/stock/fflow/kline/get?secid=1.000001&klt=1&lmt=3"
try:
    r3 = requests.get(url3, headers=h2, timeout=10, proxies=proxies)
    print(f'min params: status={r3.status_code}, len={len(r3.text)}')
    print(r3.text[:300])
except Exception as e:
    print(f'min params: {e}')
