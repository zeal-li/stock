import requests, os, json
os.environ['no_proxy'] = '*'
p = {'http': None, 'https': None}
h = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://data.eastmoney.com/'}

# 尝试 kline + margin 字段
params = {'fields1': 'f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13', 'fields2': 'f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65,f66,f67,f68,f69,f70,f71,f72,f73,f74,f75,f76,f77,f78,f79,f80', 'klt': '101', 'lmt': '5', 'ut': 'b2884a393a59ad64002292a3e90d46a5'}

for secid in ['1.000001', '90.BK0597']:
    try:
        r = requests.get('https://push2delay.eastmoney.com/api/qt/stock/kline/get', params={**params, 'secid': secid}, headers=h, timeout=10, proxies=p)
        d = r.json()
        kl = (d.get('data') or {}).get('klines') or []
        print(f'{secid}: {len(kl)} klines')
        if kl:
            k = kl[0]
            parts = str(k).split(',')
            print(f'  fields: {len(parts)}, sample: {k[:200]}')
    except Exception as e:
        print(f'{secid}: {e}')
    print('---')
