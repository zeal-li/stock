import requests, json, os
os.environ['no_proxy'] = '*'
proxies = {'http': None, 'https': None}
headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36', 'Referer': 'https://www.10jqka.com.cn/'}

apis = [
    ("同花顺资金流向", "https://dq.10jqka.com.cn/fuyao/market_analysis_api/chart/v1/get_chart_data?chart_key=fund_flow_minute"),
    ("同花顺主力资金", "https://dq.10jqka.com.cn/fuyao/market_analysis_api/chart/v1/get_chart_data?chart_key=main_force_minute"),
]

for name, url in apis:
    try:
        r = requests.get(url, headers=headers, timeout=10, proxies=proxies)
        d = r.json()
        code = d.get('status_code', d.get('code', '?'))
        pts = len(d.get('data', {}).get('charts', {}).get('point_list', []))
        print(f'{name}: status={code}, points={pts}')
        if pts > 0:
            pl = d['data']['charts']['point_list']
            print(f'  首点: {pl[0]}  末点: {pl[-1]}')
    except Exception as e:
        print(f'{name}: Error - {e}')
    print('---')
