import requests, json, os
os.environ['no_proxy'] = '*'
proxies = {'http': None, 'https': None}
headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36', 'Referer': 'https://www.eastmoney.com/'}

# 用能工作的那个 API
url = "https://push2.eastmoney.com/api/qt/stock/fflow/kline/get"
params = {
    'secid': '1.000001',
    'fields1': 'f1,f2,f3,f7',
    'fields2': 'f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65',
    'klt': '1',
    'lmt': '240'
}
r = requests.get(url, params=params, headers=headers, timeout=15, proxies=proxies)
data = r.json()

klines = data.get('data', {}).get('klines', [])
print(f'数据点: {len(klines)}')

day_groups = {}
for k in klines:
    parts = k.split(',')
    if len(parts) >= 2:
        dt_str = parts[0].split(' ')[0]
        day_groups.setdefault(dt_str, []).append(k)

latest = sorted(day_groups.keys())[-1]
today_data = day_groups[latest]
print(f'最新日: {latest}, 点数: {len(today_data)}')

for k in today_data[:3]:
    parts = k.split(',')
    print(f'{parts[0]}  主力净流入: {float(parts[1])/1e8:.2f}亿  超大单: {float(parts[5])/1e8:.2f}亿')
print('...')
for k in today_data[-3:]:
    parts = k.split(',')
    print(f'{parts[0]}  主力净流入: {float(parts[1])/1e8:.2f}亿  超大单: {float(parts[5])/1e8:.2f}亿')
