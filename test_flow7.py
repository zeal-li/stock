import requests, re, json, os
from bs4 import BeautifulSoup
os.environ['no_proxy'] = '*'
proxies = {'http': None, 'https': None}
h = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
     'Referer': 'https://www.10jqka.com.cn/'}

# 尝试同花顺首页抓取大盘资金流向
url = "https://www.10jqka.com.cn/"
r = requests.get(url, headers=h, timeout=10, proxies=proxies)
r.encoding = 'utf-8'
soup = BeautifulSoup(r.text, 'lxml')

# 查找资金流向相关数据
print("=== 查找 script 中可能含资金数据的部分 ===")
scripts = soup.find_all('script')
for s in scripts:
    if s.string and ('fund' in s.string.lower() or 'zjl' in s.string.lower() or 'flow' in s.string.lower()):
        print(s.string[:500])
        print('---')

print("\n=== 查找文本中资金相关 ===")
for el in soup.find_all(text=re.compile(r'资金|流入|流出|净流入')):
    parent = el.parent
    print(f'{parent.name}: {el.strip()[:100]}')
