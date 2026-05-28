import akshare as ak, os, inspect
os.environ['no_proxy'] = '*'

# 检查函数签名
for fn in [ak.stock_margin_sse, ak.stock_margin_szse]:
    sig = inspect.signature(fn)
    print(f'{fn.__name__}: {sig}')
print('---')

# 尝试带日期范围
try:
    df = ak.stock_margin_sse(start_date="20260525", end_date="20260528")
    print(f'沪市 5日: {len(df)} rows')
    print(df.to_string())
except Exception as e:
    print(f'沪市 range: {e}')

print('---')

try:
    df2 = ak.stock_margin_szse(start_date="20260525", end_date="20260528")
    print(f'深市 5日: {len(df2)} rows')
    print(df2.to_string())
except Exception as e:
    print(f'深市 range: {e}')
