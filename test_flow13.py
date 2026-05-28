import requests, os
os.environ['no_proxy'] = '*'
proxies = {'http': None, 'https': None}
h = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

url = "http://nufm.dfcfw.com/EM_Finance2014NumericApplication/JS.aspx?type=CT&cmd=C._A&sty=DCRRBK&st=(BalFlowMain)&sr=-1&p=1&ps=5&js=var%20data={pages:(pc),data:[(x)]}&token=7bc05d0d4c3c22ef9fca8c2a912d779c"
r = requests.get(url, headers=h, timeout=10, proxies=proxies)
r.encoding = 'gbk'
text = r.text[:3000]
print(text[:2000])

print('\n=== 解析试探 ===')
# 新API: push2.eastmoney.com 用 params dict
url2 = "https://push2.eastmoney.com/api/qt/stock/fflow/kline/get?secid=1.000001&fields1=f1,f2,f3,f7&fields2=f51,f52&klt=1&lmt=3"
try:
    r2 = requests.get(url2, headers={**h, 'Referer':'https://data.eastmoney.com/zjlx/'}, timeout=10, proxies=proxies)
    print(f'带referer: status={r2.status_code}, len={len(r2.text)}')
    d = r2.json()
    print(d)
except Exception as e:
    print(f'带referer失败: {e}')
