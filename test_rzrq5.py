import requests, re, os
os.environ['no_proxy'] = '*'
p = {'http': None, 'https': None}
h = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://data.eastmoney.com/'}

r = requests.get('https://data.eastmoney.com/rzrq/detail/all.html', headers=h, timeout=10, proxies=p)
r.encoding = 'utf-8'

# 找嵌入的 JSON 数据
patterns = [
    r'var\s+data\s*=\s*(\[.*?\]);',
    r'"total_bail"\s*:\s*"([^"]*)"',
    r'"totalBalance"\s*:\s*"?([\d.]+)"?',
    r'融资余额[^\d]*([\d,.]+[万亿]?)',
    r'融券余额[^\d]*([\d,.]+[万亿]?)',
]

for pat in patterns:
    matches = re.findall(pat, r.text, re.IGNORECASE)
    if matches:
        print(f'Pattern: {pat[:50]}...')
        for m in matches[:3]:
            print(f'  {str(m)[:100]}')
        print('---')

# 找 script 中可用的数据源
scripts = re.findall(r'<script[^>]*>(.*?)</script>', r.text, re.DOTALL)
for s in scripts:
    if ('rzrq' in s.lower() or 'margin' in s.lower() or '融资' in s) and len(s) > 50:
        print(f'Script: {s[:500]}')
        print('===')
