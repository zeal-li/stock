"""测试：能否从同花顺概念板块资金流向中获取行情级数据"""
import requests, json, os, re
from bs4 import BeautifulSoup
os.environ['no_proxy'] = '*'
proxies = {'http': None, 'https': None}
h = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36', 'Referer': 'https://data.10jqka.com.cn/'}

# 尝试同花顺大盘资金流 API（使用他们前端可能调用的接口）
urls = [
    "https://data.10jqka.com.cn/funds/ajax/getFundFlow?code=sh000001",
    "https://d.10jqka.com.cn/v6/line/hs_000001/01/last.js",
    "https://dq.10jqka.com.cn/fuyao/market_analysis_api/chart/v1/get_chart_data?chart_key=fundflow_minute",
    "https://dq.10jqka.com.cn/fuyao/market_analysis_api/chart/v1/get_chart_data?chart_key=funds_flow",
    "https://dq.10jqka.com.cn/fuyao/market_analysis_api/chart/v1/get_chart_data?chart_key=main_fund",
    "https://dq.10jqka.com.cn/fuyao/market_analysis_api/chart/v1/get_chart_data?chart_key=net_inflow",
]

for url in urls:
    try:
        r = requests.get(url, headers=h, timeout=10, proxies=proxies)
        print(f'{url.split("chart_key=")[-1] if "chart_key" in url else url.split("/")[-1]}: status={r.status_code}, len={len(r.text)}')
        if r.status_code == 200 and len(r.text) > 100:
            try:
                d = r.json()
                print(f'  json: {json.dumps(d, ensure_ascii=False)[:300]}')
            except:
                print(f'  text: {r.text[:200]}')
    except Exception as e:
        print(f'{url.split("/")[-1][:30]}: {e}')
    print('---')
