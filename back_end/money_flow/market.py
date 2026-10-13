"""大盘行情、分时走势、涨跌分布、日K收盘价"""
import datetime
from common.http import get_realtime_quotes_ulist, get_em_trends, get_tx_kline, get_json, HEADERS_EM_DATA
from money_flow.storage import save_field, get_field


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
                save_field('indices', {'success': True, 'data': data})
                return True
    except Exception as e:
        print(f"[major-indices poller] fetch error: {e}")
    return False


# 涨跌分布区间标签（东财 getTopicZDFenBu 的 key 为涨跌幅整数区间）
_DIST_BUCKETS = {
    '-11': '跌停',
    '-10': '-10%~-9%',
    '-9': '-9%~-8%',
    '-8': '-8%~-7%',
    '-7': '-7%~-6%',
    '-6': '-6%~-5%',
    '-5': '-5%~-4%',
    '-4': '-4%~-3%',
    '-3': '-3%~-2%',
    '-2': '-2%~-1%',
    '-1': '-1%~0%',
    '0': '平盘',
    '1': '0%~1%',
    '2': '1%~2%',
    '3': '2%~3%',
    '4': '3%~4%',
    '5': '4%~5%',
    '6': '5%~6%',
    '7': '6%~7%',
    '8': '7%~8%',
    '9': '8%~9%',
    '10': '9%~10%',
    '11': '涨停',
}
_DIST_URL = 'https://push2ex.eastmoney.com/getTopicZDFenBu'
_DIST_UT = '7eea3edcaed734bea9cbfc24409ed989'


def _fetch_and_cache_distribution():
    """抓取沪深涨跌分布并写入缓存（走东财 getTopicZDFenBu，单一数据源）"""
    try:
        body = get_json(_DIST_URL, params={'ut': _DIST_UT, 'dpt': 'wz.ztzt'},
                        headers=HEADERS_EM_DATA, timeout=10)
        fenbu = (body.get('data') or {}).get('fenbu') or []
        labels, counts = [], []
        for key in sorted(_DIST_BUCKETS, key=lambda k: int(k)):
            count = 0
            for item in fenbu:
                v = item.get(key)
                if v is not None:
                    count = int(v)
                    break
            labels.append(_DIST_BUCKETS[key])
            counts.append(count)
        rise = fall = flat = limit_up = limit_down = 0
        for label, count in zip(labels, counts):
            if label == '跌停':
                limit_down = count
                fall += count
            elif label == '涨停':
                limit_up = count
                rise += count
            elif label == '平盘':
                flat = count
            elif label.startswith('-'):
                fall += count
            else:
                rise += count

        result = {
            'success': True,
            'data': {
                'labels': labels, 'counts': counts,
                'rise': rise, 'fall': fall, 'flat': flat,
                'limit_up': limit_up, 'limit_down': limit_down,
            }
        }
        save_field('distribution', result)
        return True
    except Exception as e:
        print(f"[distribution poller] fetch error: {e}")
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
        save_field('sh_minute', result)
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
        save_field('daily_closes', result)
        return True
    except Exception as e:
        print(f"[daily-closes poller] fetch error: {e}")
    return False


def get_major_indices():
    """上证指数实时行情（从快照读取）"""
    val = get_field('indices')
    if val:
        return val
    return {'success': False, 'error': '暂无指数数据'}


def get_sh000001_minute_data():
    """上证指数分时走势（从快照读取）"""
    val = get_field('sh_minute')
    if val:
        return val
    return {'success': False, 'error': '暂无分时数据'}


def get_index_minute_data():
    """成交额分时数据（从快照读取）"""
    val = get_field('turnover')
    if val:
        return val
    return {'success': False, 'error': '暂无成交额数据'}


def get_market_distribution():
    """沪深涨跌分布（优先读快照，快照空时同步抓取，单一数据源）"""
    val = get_field('distribution')
    if val:
        return val
    _fetch_and_cache_distribution()
    val = get_field('distribution')
    if val:
        return val
    return {'success': False, 'error': '暂无涨跌分布数据'}
