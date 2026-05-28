import akshare as ak, os
os.environ['no_proxy'] = '*'

# 尝试不同融资融券函数
funcs = [
    ("沪市汇总", ak.stock_margin_sse, "20250401"),
    ("深市汇总", ak.stock_margin_szse, "20250401"),
]

for name, func, arg in funcs:
    try:
        df = func(arg)
        print(f'{name}: {len(df)} rows')
        print(f'  columns: {df.columns.tolist()[:10]}')
        print(f'  head: {df.head(2).to_string()}')
    except Exception as e:
        print(f'{name}: {type(e).__name__}: {e}')
    print('---')
