import requests, json, os
os.environ['no_proxy'] = '*'
proxies = {'http': None, 'https': None}
h = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://www.10jqka.com.cn/'}

# 查看空响应内容
url = "https://dq.10jqka.com.cn/fuyao/market_analysis_api/chart/v1/get_chart_data?chart_key=fundflow_minute"
r = requests.get(url, headers=h, timeout=10, proxies=proxies)
print(f"status: {r.status_code}")
print(f"body: '{r.text}'")

# 换用同花顺的 auth 接口
print("\n=== 尝试 auth ===")
auth_url = "https://dq.10jqka.com.cn/fuyao/market_analysis_api/auth/getToken"
r2 = requests.get(auth_url, headers=h, timeout=10, proxies=proxies)
print(f"auth: status={r2.status_code}, body='{r2.text[:200]}'")

# 尝试带 token 的请求
print("\n=== 带 token 请求 ===")
r3 = requests.get(
    "https://dq.10jqka.com.cn/fuyao/market_analysis_api/chart/v1/get_chart_data",
    params={'chart_key': 'turnover_minute'},
    headers={**h, 'Cookie': r.cookies},
    timeout=10, proxies=proxies
)
d = r3.json()
print(f"turnover_minute: status_code={d.get('status_code')}, points={len(d.get('data',{}).get('charts',{}).get('point_list',[]))}")
