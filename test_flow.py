import requests, json, os
os.environ['no_proxy'] = '*'
proxies = {'http': None, 'https': None}
headers = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://www.eastmoney.com/'}

# 尝试东方财富大盘资金流向 API
urls = [
    "https://push2.eastmoney.com/api/qt/stock/fflow/kline/get?secid=1.000001&fields1=f1,f2,f3,f7&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65&klt=1&lmt=5",
]

for url in urls:
    try:
        r = requests.get(url, headers=headers, timeout=10, proxies=proxies)
        print(f"URL: {url[:80]}...")
        data = r.json()
        print(json.dumps(data, indent=2, ensure_ascii=False)[:2000])
        print("---")
    except Exception as e:
        print(f"Error: {e}")
        print("---")
