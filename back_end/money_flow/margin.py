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

    # 上交所 + 深交所合并（先放 SSE）
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

    # 深交所 — 按 SSE 已有日期逐日查询，字段名 jrrzye/jrrjye/jrrzrjye/jrrzmr，单位已是亿
    szse_dates = sorted(combined.keys())
    try:
        session = _rq.Session()
        session.headers.update({**_MARGIN_HEADERS, 'Referer': 'https://www.szse.cn/'})
        for d in szse_dates:
            fmt_date = d[:4] + '-' + d[4:6] + '-' + d[6:8]
            try:
                r_sz = session.get('https://www.szse.cn/api/report/ShowReport/data', params={
                    'SHOWTYPE': 'json',
                    'CATALOGID': '1837_xxpl',
                    'txtDate': fmt_date,
                    'tab1PAGENO': '1',
                    'tab1PAGESIZE': '500',
                    'random': '0.5',
                }, timeout=10)
                sz_data = r_sz.json()
                if isinstance(sz_data, list) and len(sz_data) > 0:
                    rows = sz_data[0].get('data', [])
                    if rows:
                        row = rows[0]
                        def _sz_val(key):
                            v = str(row.get(key, '0')).replace(',', '')
                            return float(v) if v else 0.0
                        # SZSE 已是亿元，×1e8 转回元与 SSE 统一
                        combined[d]['rz'] += _sz_val('jrrzye') * 1e8
                        combined[d]['rq'] += _sz_val('jrrjye') * 1e8
                        combined[d]['total'] += _sz_val('jrrzrjye') * 1e8
                        combined[d]['buy'] += _sz_val('jrrzmr') * 1e8
            except Exception:
                pass
    except Exception as e:
        print(f'[margin] SZSE error: {e}')

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
