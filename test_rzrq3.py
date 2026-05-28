import requests, os, json
os.environ['no_proxy'] = '*'
p = {'http': None, 'https': None}
h = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36', 'Referer': 'https://data.eastmoney.com/rzrq/'}

tests = [
    ("东财 RZRQ 详情页 JSON", "https://data.eastmoney.com/rzrq/api/data/get?type=0&page=1&size=5"),
    ("东财 RZRQ 全市场", "https://data.eastmoney.com/rzrq/detail/all.html"),
    ("同花顺 RZRQ", "https://data.10jqka.com.cn/funds/rzrq/"),
]

for name, url in tests:
    try:
        r = requests.get(url, headers=h, timeout=10, proxies=p)
        if r.status_code == 200:
            try:
                d = r.json()
                print(f'{name}: JSON ok')
                print(f'  {json.dumps(d, ensure_ascii=False)[:500]}')
            except:
                txt = r.text[:400]
                if '融资' in txt or '融券' in txt or 'rzrq' in txt.lower():
                    print(f'{name}: HTML with data ({len(r.text)} chars)')
                    print(f'  {txt[:300]}')
                else:
                    print(f'{name}: HTML ({len(r.text)} chars) no visible rzrq')
        else:
            print(f'{name}: status={r.status_code}')
    except Exception as e:
        print(f'{name}: {e}')
    print('---')
