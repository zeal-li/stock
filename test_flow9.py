import requests, os, time
os.environ['no_proxy'] = '*'

session = requests.Session()
session.proxies = {'http': None, 'https': None}
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': '*/*',
    'Accept-Language': 'zh-CN,zh;q=0.9',
    'Connection': 'keep-alive',
})

# 先访问首页获取 cookies
try:
    session.get('https://www.eastmoney.com/', timeout=10)
    print('首页访问成功')
except:
    print('首页访问失败')

time.sleep(1)

# 再请求基金流 API
url = "https://push2.eastmoney.com/api/qt/stock/fflow/kline/get"
params = {
    'secid': '1.000001',
    'fields1': 'f1,f2,f3,f7',
    'fields2': 'f51,f52',
    'klt': '1',
    'lmt': '240'
}

try:
    r = session.get(url, params=params, timeout=15)
    d = r.json()
    klines = d.get('data', {}).get('klines', [])
    print(f'成功! 数据点: {len(klines)}')
    if klines:
        day_groups = {}
        for k in klines:
            p = k.split(',')
            day_groups.setdefault(p[0].split(' ')[0], []).append(k)
        latest = sorted(day_groups.keys())[-1]
        today = day_groups[latest]
        print(f'最新日: {latest}, 点数: {len(today)}')
        for i in [0, 1, 2, -3, -2, -1]:
            if 0 <= i < len(today) or (i < 0 and abs(i) <= len(today)):
                p = today[i].split(',')
                print(f'  {p[0]}  主力净流入: {float(p[1])/1e8:.2f}亿')
    else:
        print('无数据')
except Exception as e:
    print(f'失败: {e}')
