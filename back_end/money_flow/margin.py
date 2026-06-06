"""融资融券数据 — 上交所/深交所直接拉取"""
import datetime
import requests as _rq
from money_flow.storage import db_set, db_get

_MARGIN_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
}


def _fetch_and_cache_margin():
    """抓取融资融券数据并写入缓存"""
    today = datetime.date.today()
    end_str = today.strftime('%Y%m%d')
    start_str = (today - datetime.timedelta(days=60)).strftime('%Y%m%d')

    # 上交所
    sse_rows = []
    try:
        r = _rq.get('https://query.sse.com.cn/marketdata/tradedata/queryMargin.do', params={
            'isPagination': 'true',
            'beginDate': start_str,
            'endDate': end_str,
            'pageHelp.pageSize': '5000',
            'pageHelp.pageNo': '1',
        }, headers={**_MARGIN_HEADERS, 'Referer': 'https://www.sse.com.cn/'}, timeout=10)
        sse_rows = r.json().get('result', [])
    except Exception as e:
        print(f'[margin] SSE error: {e}')

    # 深交所（汇总数据）
    szse_rows = []
    try:
        # 深交所按日期逐天取
        r_sz = _rq.get('https://www.szse.cn/api/report/ShowReport/data', params={
            'SHOWTYPE': 'json',
            'CATALOGID': '1837_xxpl',
            'txtStart': start_str[:4] + '-' + start_str[4:6] + '-' + start_str[6:],
            'txtEnd': end_str[:4] + '-' + end_str[4:6] + '-' + end_str[6:],
            'tab1PAGENO': '1',
            'tab1PAGESIZE': '500',
            'random': '0.5',
        }, headers={**_MARGIN_HEADERS, 'Referer': 'https://www.szse.cn/'}, timeout=15)
        sz_data = r_sz.json()
        if isinstance(sz_data, list) and len(sz_data) > 0:
            szse_rows = sz_data[0].get('data', [])
    except Exception as e:
        print(f'[margin] SZSE error: {e}')

    # 合并
    combined = {}
    for row in sse_rows:
        d = row.get('opDate', '')
        if not d:
            continue
        combined[d] = {
            'rz': float(row.get('rzye', 0) or 0),
            'rq': float(row.get('rqylje', 0) or 0),
            'total': float(row.get('rzrqjyzl', 0) or 0),
            'buy': float(row.get('rzmre', 0) or 0),
        }

    for row in szse_rows:
        d = str(row.get('交易日期', row.get('jyDate', row.get('date', '')))).replace('-', '')
        if not d:
            continue
        rz_val = float(row.get('融资余额', row.get('rzye', 0)) or 0)
        rq_val = float(row.get('融券余额', row.get('rqye', row.get('rqylje', 0))) or 0)
        total_val = float(row.get('融资融券余额', row.get('rzrqye', 0)) or 0)
        buy_val = float(row.get('融资买入额', row.get('rzmre', 0)) or 0)
        if d in combined:
            combined[d]['rz'] += rz_val
            combined[d]['rq'] += rq_val
            combined[d]['total'] += total_val
            combined[d]['buy'] += buy_val
        else:
            combined[d] = {'rz': rz_val, 'rq': rq_val, 'total': total_val, 'buy': buy_val}

    if not combined:
        return False

    sorted_dates = sorted(combined.keys())
    dates, rz, rq, tot, buy = [], [], [], [], []
    for d in sorted_dates:
        fmt = d[:4] + '-' + d[4:6] + '-' + d[6:8]
        dates.append(fmt[-5:])
        v = combined[d]
        rz.append(round(v['rz'] / 1e8, 2))
        rq.append(round(v['rq'] / 1e8, 2))
        tot.append(round(v['total'] / 1e8, 2))
        buy.append(round(v['buy'] / 1e8, 2))

    # 计算变化率
    fin_bal_5d, fin_bal_10d, fin_buy_heat = 0.0, 0.0, 0.0
    if len(tot) >= 6:
        fin_bal_5d = round((tot[-1] - tot[-6]) / tot[-6] * 100, 2) if tot[-6] else 0
    if len(tot) >= 11:
        fin_bal_10d = round((tot[-1] - tot[-11]) / tot[-11] * 100, 2) if tot[-11] else 0
    if len(buy) >= 21:
        avg20 = sum(buy[-21:]) / 21
        fin_buy_heat = round((buy[-1] - avg20) / avg20 * 100, 2) if avg20 else 0

    result = {
        'success': True,
        'data': {
            'dates': dates, 'rz_balances': rz, 'rq_balances': rq,
            'total_balances': tot, 'buy_amounts': buy,
            'latest_date': dates[-1] if dates else '',
            'latest_rz': rz[-1] if rz else 0, 'latest_rq': rq[-1] if rq else 0,
            'latest_total': tot[-1] if tot else 0,
            'fin_bal_5d': fin_bal_5d, 'fin_bal_10d': fin_bal_10d, 'fin_buy_heat': fin_buy_heat,
        }
    }
    db_set('margin_trading', result, today.strftime('%Y-%m-%d'))
    return True


def get_margin_trading():
    row = db_get('margin_trading')
    if row:
        return row[0]
    return {'success': False, 'error': '暂无融资融券数据'}
