"""财务数据（资产负债表等）"""
import akshare as ak
import pandas as pd


def get_goodwill(codes):
    """批量获取商誉数据"""
    result = {}
    for code in codes:
        try:
            prefix = 'SH' if code.startswith(('6', '9')) else 'SZ'
            df = ak.stock_balance_sheet_by_report_em(symbol=f"{prefix}{code}")
            if df is not None and not df.empty and 'GOODWILL' in df.columns:
                gw = df.iloc[0].get('GOODWILL', 0)
                result[code] = float(gw) if pd.notna(gw) and gw else 0
            else:
                result[code] = 0
        except Exception:
            result[code] = 0
    return result
