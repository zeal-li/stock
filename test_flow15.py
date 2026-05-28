import requests, re, os
os.environ['no_proxy'] = '*'
proxies = {'http': None, 'https': None}
h = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36', 'Referer': 'https://www.eastmoney.com/'}

# 1. 东方财富资金流数据页面 - 找JSON数据
url = "https://data.eastmoney.com/zjlx/"
r = requests.get(url, headers=h, timeout=10, proxies=proxies)
r.encoding = 'utf-8'

# 找页面中的 JSON 数据块
json_blocks = re.findall(r'\{(?:[^{}]|(?:\{[^{}]*\}))*\}', r.text)
for i, block in enumerate(json_blocks):
    if 'fund' in block.lower() or 'flow' in block.lower() or 'zjlx' in block.lower() or 'jlr' in block.lower():
        print(f'JSON block {i}: {block[:500]}')
        print('---')

# 2. 尝试旧东方财富API解码
print('\n=== 旧API数据 ===')
url2 = "http://nufm.dfcfw.com/EM_Finance2014NumericApplication/JS.aspx?type=CT&cmd=C._A&sty=DCRRBK&st=(BalFlowMain)&sr=-1&p=1&ps=3&js=var%20data={pages:(pc),data:[(x)]}&token=7bc05d0d4c3c22ef9fca8c2a912d779c"
r2 = requests.get(url2, headers=h, timeout=10, proxies=proxies)
r2.encoding = 'gb18030'
# 提取 data 部分
match = re.search(r'data:\[(.*?)\]\}', r2.text, re.DOTALL)
if match:
    items = match.group(1).replace('"', '').split('","')
    for item in items[:3]:
        print(item[:200])
