import requests, os
os.environ['no_proxy'] = '*'
proxies = {'http': None, 'https': None}
h = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36', 'Referer': 'https://data.eastmoney.com/'}

# 东方财富 资金流 API - 市场级别
apis = [
    ("全市场资金流", "https://push2.eastmoney.com/api/qt/clt/get?fid=f62&po=1&pz=3&pn=1&np=1&fltt=2&invt=2&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23&fields=f12,f14,f2,f3,f62,f184,f66"),
    ("上证指数", "https://push2.eastmoney.com/api/qt/stock/get?secid=1.000001&fields=f43,f44,f45,f46,f47,f48,f49,f50,f51,f52,f57,f58,f60,f116,f117,f161,f162,f163,f164,f165,f166,f167,f168,f169,f170,f171"),
    ("大盘资金页", "https://data.eastmoney.com/zjlx/dpzjlx.html"),
]

for name, url in apis:
    try:
        r = requests.get(url, headers=h, timeout=10, proxies=proxies)
        if r.status_code == 200:
            try:
                d = r.json()
                print(f'{name}: OK - {str(d)[:300]}')
            except:
                text = r.text[:300]
                if '主力' in text or '资金' in text:
                    import re
                    nums = re.findall(r'[-+]?\d+\.?\d*[万亿]', text)
                    print(f'{name}: HTML ({len(r.text)} chars) - {nums[:10]}')
                else:
                    print(f'{name}: {text[:150]}')
        else:
            print(f'{name}: status={r.status_code}')
    except Exception as e:
        print(f'{name}: FAIL - {e}')
    print('---')
