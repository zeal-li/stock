import requests, os
os.environ['no_proxy'] = '*'
proxies = {'http': None, 'https': None}
h = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

tests = [
    ("东方财富-lmt5", "https://push2.eastmoney.com/api/qt/stock/fflow/kline/get?secid=1.000001&fields1=f1,f2,f3,f7&fields2=f51,f52&klt=1&lmt=5"),
    ("东方财富-nofield2", "https://push2.eastmoney.com/api/qt/stock/fflow/kline/get?secid=1.000001&fields1=f1,f2,f3,f7&klt=1&lmt=5"),
    ("新浪-大盘资金", "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/MoneyFlow.ssl_qsfx_zjlr?page=1&num=5&sort=opendate&asc=0"),
    ("同花顺-大盘资金页", "https://data.10jqka.com.cn/funds/dpzjl/field/zjlr/order/desc/page/1/ajax/1/free/1/"),
    ("东方财富-market", "https://push2.eastmoney.com/api/qt/ulist.np/get?fltt=2&secids=1.000001&fields=f2,f3,f4,f8,f9,f10,f12,f14,f15,f16,f17,f18,f20,f21,f62,f184,f66,f69,f72,f75,f78,f81,f84,f87"),
]

for name, url in tests:
    try:
        r = requests.get(url, headers=h, timeout=10, proxies=proxies)
        text = r.text[:500]
        if r.status_code == 200 and len(text) > 10:
            print(f'{name}: OK ({len(text)} chars) - {text[:200]}')
        else:
            print(f'{name}: status={r.status_code}, len={len(text)}')
    except Exception as e:
        print(f'{name}: FAIL - {str(e)[:80]}')
    print('---')
