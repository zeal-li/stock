import requests, json, os
os.environ['no_proxy'] = '*'
proxies = {'http': None, 'https': None}

session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Referer': 'https://www.eastmoney.com/',
    'Accept': '*/*',
})

# 用 work 的 URL 格式 + lmt=240
url = "https://push2.eastmoney.com/api/qt/stock/fflow/kline/get?secid=1.000001&fields1=f1,f2,f3,f7&fields2=f51,f52&klt=1&lmt=240"
try:
    r = session.get(url, timeout=15, proxies=proxies)
    d = r.json()
    klines = d.get('data', {}).get('klines', [])
    print(f'成功! 数据点: {len(klines)}')
    if klines:
        day_groups = {}
        for k in klines:
            p = k.split(',')
            day_groups.setdefault(p[0].split(' ')[0], []).append(k)
        latest = sorted(day_groups.keys())[-1]
        print(f'最新日: {latest}, 点数: {len(day_groups[latest])}')
        for k in day_groups[latest][:3]:
            p = k.split(',')
            print(f'  {p[0]}  主力净流入: {float(p[1])/1e8:.2f}亿')
except Exception as e:
    print(f'失败: {e}')
