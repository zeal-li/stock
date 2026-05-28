import requests, json, os, time
os.environ['no_proxy'] = '*'
proxies = {'http': None, 'https': None}
headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36', 'Referer': 'https://www.eastmoney.com/'}

url = "https://push2.eastmoney.com/api/qt/stock/fflow/kline/get"
params = {'secid': '1.000001', 'fields1': 'f1,f2,f3,f7', 'fields2': 'f51,f52', 'klt': '1', 'lmt': '240'}

for attempt in range(3):
    try:
        time.sleep(2 * attempt)
        r = requests.get(url, params=params, headers=headers, timeout=15, proxies=proxies)
        data = r.json()
        klines = data.get('data', {}).get('klines', [])
        print(f'第{attempt+1}次尝试成功! 数据点: {len(klines)}')
        if klines:
            day_groups = {}
            for k in klines:
                parts = k.split(',')
                dt_str = parts[0].split(' ')[0]
                day_groups.setdefault(dt_str, []).append(k)
            latest = sorted(day_groups.keys())[-1]
            print(f'最新日: {latest}, 点数: {len(day_groups[latest])}')
            for k in day_groups[latest][:2]:
                p = k.split(',')
                print(f'  {p[0]}  主力净流入: {float(p[1])/1e8:.2f}亿')
        break
    except Exception as e:
        print(f'第{attempt+1}次失败: {e}')
