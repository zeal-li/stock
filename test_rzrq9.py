import akshare as ak, os
os.environ['no_proxy'] = '*'

# 测试 akshare 融资融券数据
try:
    df = ak.stock_margin_detail_sse(date="20260528")
    print(f'沪深融资融券详情: {len(df)} rows')
    print(df.head())
    print('---')
    print(df.columns.tolist())
except Exception as e:
    print(f'Error: {e}')
    # 尝试其他函数
    try:
        df2 = ak.stock_margin_underlying_info_szse()
        print(f'深市: {len(df2)} rows')
    except Exception as e2:
        print(f'深市: {e2}')
