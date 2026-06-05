"""融资融券数据"""
import datetime
from concurrent.futures import ThreadPoolExecutor
from money_flow.storage import db_set, db_get, _MARGIN_KEY


def _fetch_and_cache_margin():
    """抓取融资融券沪深两市数据并写入缓存（供图表+风险指数共用）"""
    try:
        import akshare as ak
        end_date = datetime.date.today().strftime('%Y%m%d')
        start_date = (datetime.date.today() - datetime.timedelta(days=60)).strftime('%Y%m%d')

        def _get_df(func, *args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception:
                return None

        with ThreadPoolExecutor(max_workers=2) as pool:
            fut_sse = pool.submit(_get_df, ak.stock_margin_sse, start_date=start_date, end_date=end_date)
            fut_szse = pool.submit(_get_df, ak.stock_margin_szse, start_date=start_date, end_date=end_date)
            sse_df = fut_sse.result()
            szse_df = fut_szse.result()

        combined = {}
        for df in [sse_df, szse_df]:
            if df is not None and not df.empty:
                for _, row in df.iterrows():
                    d = str(row['信用交易日期'])
                    rz_val = float(row.get('融资余额', 0) or 0) / 1e8
                    rq_val = float(row.get('融券余量金额', 0) or 0) / 1e8
                    total_val = float(row.get('融资融券余额', 0) or 0) / 1e8
                    buy_val = float(row.get('融资买入额', 0) or 0) / 1e8
                    if d not in combined:
                        combined[d] = [rz_val, rq_val, total_val, buy_val]
                    else:
                        combined[d][0] += rz_val
                        combined[d][1] += rq_val
                        combined[d][2] += total_val
                        combined[d][3] += buy_val

        if not combined:
            return False

        sorted_dates = sorted(combined.keys())
        dates, rz_balances, rq_balances, total_balances, buy_amounts = [], [], [], [], []
        for d in sorted_dates:
            fmt_d = d[:4] + '-' + d[4:6] + '-' + d[6:8]
            dates.append(fmt_d[-5:])
            rz_balances.append(round(combined[d][0], 2))
            rq_balances.append(round(combined[d][1], 2))
            total_balances.append(round(combined[d][2], 2))
            buy_amounts.append(round(combined[d][3], 2))

        latest = combined[sorted_dates[-1]]
        fin_data = {}
        if len(sorted_dates) >= 2:
            latest_total = latest[2]
            latest_buy = latest[3]
            if len(sorted_dates) >= 6:
                t5_total = combined[sorted_dates[-6]][2]
                fin_data['fin_bal_5d'] = round((latest_total - t5_total) / t5_total * 100, 2) if t5_total else 0
            if len(sorted_dates) >= 11:
                t10_total = combined[sorted_dates[-11]][2]
                fin_data['fin_bal_10d'] = round((latest_total - t10_total) / t10_total * 100, 2) if t10_total else 0
            if len(sorted_dates) >= 21:
                recent_buys = [combined[d][3] for d in sorted_dates[-21:]]
                avg_20d = sum(recent_buys) / len(recent_buys) if recent_buys else 0
                fin_data['fin_buy_heat'] = round((latest_buy - avg_20d) / avg_20d * 100, 2) if avg_20d else 0

        result = {
            'success': True,
            'data': {
                'dates': dates, 'rz_balances': rz_balances, 'rq_balances': rq_balances,
                'total_balances': total_balances, 'buy_amounts': buy_amounts,
                'latest_date': dates[-1] if dates else '',
                'latest_rz': round(latest[0], 2),
                'latest_rq': round(latest[1], 2),
                'latest_total': round(latest[2], 2),
                'fin_bal_5d': fin_data.get('fin_bal_5d', 0.0),
                'fin_bal_10d': fin_data.get('fin_bal_10d', 0.0),
                'fin_buy_heat': fin_data.get('fin_buy_heat', 0.0),
            }
        }
        db_set(_MARGIN_KEY, result, datetime.date.today().strftime('%Y-%m-%d'))
        return True
    except Exception as e:
        print(f"[margin poller] fetch error: {e}")
    return False


def get_margin_trading():
    """融资融券数据（从缓存读取）"""
    row = db_get(_MARGIN_KEY)
    if row:
        return row[0]
    return {'success': False, 'error': '暂无融资融券数据'}
