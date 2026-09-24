"""大盘行情、分时走势、涨跌家数、日K收盘价"""
import datetime
import time
from common.http import get_realtime_quotes_ulist, get_em_trends, get_tx_kline
from money_flow.storage import db_set, db_get, db_has, _MAJOR_INDICES_KEY, _MARKET_BREADTH_KEY, _SH_MINUTE_KEY, _TURNOVER_MINUTE_KEY, _DAILY_CLOSES_KEY


def _fetch_and_cache_major_indices():
    """抓取沪深指数行情并写入缓存（走 common.http.get_realtime_quotes_ulist）"""
    try:
        quotes = get_realtime_quotes_ulist('1.000001,0.399001')
        if quotes:
            data = []
            for q in quotes.values():
                price = q['price']
                change_pct = q['pct']
                change_val = q['change']
                data.append({
                    'code': q['code'],
                    'name': q['name'],
                    'price': f"{price:.2f}" if price is not None else '-',
                    'change': f"{'+' if change_pct is not None and change_pct >= 0 else ''}{change_pct:.2f}%" if change_pct is not None else '0.00%',
                    'change_value': f"{'+' if change_val is not None and change_val >= 0 else ''}{change_val:.2f}" if change_val is not None else '+0.00',
                })
            if data:
                db_set(_MAJOR_INDICES_KEY, {'success': True, 'data': data}, time.time())
                return True
    except Exception as e:
        print(f"[major-indices poller] fetch error: {e}")
    return False


def _fetch_and_cache_breadth():
    """抓取沪深涨跌家数并写入缓存（走 common.http.get_realtime_quotes_ulist）"""
    try:
        quotes = get_realtime_quotes_ulist('1.000001,0.399001')
        rise = sum(int(q['rise'] or 0) for q in quotes.values())
        fall = sum(int(q['fall'] or 0) for q in quotes.values())
        db_set(_MARKET_BREADTH_KEY, [rise, fall], time.time())
        return True
    except Exception as e:
        print(f"[breadth poller] fetch error: {e}")
    return False


def _fetch_and_cache_sh_minute():
    """抓取上证分时走势并写入缓存（走 common.http.get_em_trends）"""
    try:
        td = get_em_trends('1.000001')
        points = td['points']
        pre_close = td['pre_close'] or 0
        times, prices = [], []
        for p in points:
            if p['time'] < '09:30':
                continue
            times.append(p['time'])
            prices.append(p['price'])
        cp = prices[-1] if prices else pre_close
        cv = cp - pre_close if pre_close else 0
        cpt = (cv / pre_close * 100) if pre_close else 0
        result = {
            'success': True,
            'data': {
                'name': td['name'] or '上证指数',
                'preClose': pre_close,
                'currentPrice': cp,
                'change': f"{'+' if cpt >= 0 else ''}{cpt:.2f}%",
                'changeValue': f"{'+' if cv >= 0 else ''}{cv:.2f}",
                'times': times, 'prices': prices,
            }
        }
        db_set(_SH_MINUTE_KEY, result, time.time())
        return True
    except Exception as e:
        print(f"[sh-minute poller] fetch error: {e}")
    return False


def _fetch_and_cache_daily_closes():
    """抓取沪深指数30天日K收盘价并写入缓存（走 common.http.get_tx_kline）"""
    try:
        result = {}
        for symbol in ['sh000001', 'sz399001']:
            kline = get_tx_kline(symbol, 30)
            result[symbol] = [row['close'] for row in kline['rows']]
        db_set(_DAILY_CLOSES_KEY, result, datetime.date.today().strftime('%Y-%m-%d'))
        return True
    except Exception as e:
        print(f"[daily-closes poller] fetch error: {e}")
    return False


def get_major_indices():
    """上证指数实时行情（从缓存读取）"""
    row = db_get(_MAJOR_INDICES_KEY)
    if row:
        return row[0]
    return {'success': False, 'error': '暂无指数数据'}


def get_sh000001_minute_data():
    """上证指数分时走势（从缓存读取）"""
    row = db_get(_SH_MINUTE_KEY)
    if row:
        return row[0]
    return {'success': False, 'error': '暂无分时数据'}


def get_index_minute_data():
    """成交额分时数据（从缓存读取）"""
    row = db_get(_TURNOVER_MINUTE_KEY)
    if row:
        return row[0]
    return {'success': False, 'error': '暂无成交额数据'}
