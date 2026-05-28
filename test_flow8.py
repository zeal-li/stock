import requests, json, os
os.environ['no_proxy'] = '*'
proxies = {'http': None, 'https': None}
h = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36', 'Referer': 'https://www.10jqka.com.cn/'}

apis = [
    ("THS-指数资金", "https://data.10jqka.com.cn/funds/zzzjl/"),
    ("THS-概念资金", "https://data.10jqka.com.cn/funds/gnzjl/"),
    ("THS-大盘资金", "https://data.10jqka.com.cn/funds/dpzjl/"),
    ("THS-大盘资金2", "https://data.10jqka.com.cn/funds/sczjl/"),
    ("THS-上证资金", "https://data.10jqka.com.cn/funds/szzjl/"),
]

for name, url in apis:
    try:
        r = requests.get(url, headers=h, timeout=10, proxies=proxies)
        text = r.text[:300]
        status = r.status_code
        if 'zjl' in text.lower() or '资金' in text or '净流入' in text:
            print(f'{name}: OK({status}) - {text[:200]}')
        else:
            print(f'{name}: status={status}, len={len(r.text)}')
    except Exception as e:
        print(f'{name}: FAIL - {e}')
    print('---')
