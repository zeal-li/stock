import requests, os
os.environ['no_proxy'] = '*'
proxies = {'http': None, 'https': None}
h = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
url = "http://nufm.dfcfw.com/EM_Finance2014NumericApplication/JS.aspx?type=CT&cmd=C._A&sty=DCRRBK&st=(BalFlowMain)&sr=-1&p=1&ps=5&js=var%20data={pages:(pc),data:[(x)]}&token=7bc05d0d4c3c22ef9fca8c2a912d779c"
try:
    r = requests.get(url, headers=h, timeout=10, proxies=proxies)
    print(f'HTTP API: status={r.status_code}, len={len(r.text)}')
    print(r.text[:500])
except Exception as e:
    print(f'HTTP API: {e}')

# 试试数据页面
print('\n=== 东方财富资金流页面 ===')
url2 = "https://data.eastmoney.com/zjlx/"
try:
    r2 = requests.get(url2, headers={**h, 'Referer':'https://www.eastmoney.com/'}, timeout=10, proxies=proxies)
    print(f'status={r2.status_code}, len={len(r2.text)}')
    import re
    matches = re.findall(r'主力净流入[^<]*<[^>]*>([^<]+)', r2.text)
    print(f'主力净流入匹配: {matches[:5]}')
except Exception as e:
    print(f'{e}')
