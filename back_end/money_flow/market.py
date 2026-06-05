"""大盘行情、分时走势、涨跌家数、日K收盘价"""
import datetime
import time
import requests
from common import REQUEST_PROXIES
from money_flow.cache import _cache, _EM_HEADERS, _EM_UT, _MAJOR_INDICES_KEY, _MARKET_BREADTH_KEY, _SH_MINUTE_KEY, _TURNOVER_MINUTE_KEY, _DAILY_CLOSES_KEY


def _fetch_and_cache_major_indices():
    """抓取沪深指数行情并写入缓存"""
    try:
        url = "https://push2delay.eastmoney.com/api/qt/ulist.np/get"
        params = {
            'fltt': 2, 'invt': 2,
            'fields': 'f2,f3,f4,f12,f14',
            'secids': '1.000001,0.399001',
            'ut': _EM_UT,
        }
        r = requests.get(url, params=params, headers=_EM_HEADERS, timeout=8, proxies=REQUEST_PROXIES)
        diff = (r.json().get('data') or {}).get('diff') or []
        if diff:
            data = []
            for row in diff:
                code = row.get('f12', '')
                name = row.get('f14', '')
                price = row.get('f2')
                change_pct = row.get('f3')
                change_val = row.get('f4')
                data.append({
                    'code': code,
                    'name': name,
                    'price': f"{float(price):.2f}" if price else '-',
                    'change': f"{'+' if change_pct and float(change_pct) >= 0 else ''}{float(change_pct):.2f}%" if change_pct is not None else '0.00%',
                    'change_value': f"{'+' if change_val and float(change_val) >= 0 else ''}{float(change_val):.2f}" if change_val is not None else '+0.00',
                })
            if data:
                _cache[_MAJOR_INDICES_KEY] = ({'success': True, 'data': data}, time.time())
                return True
    except Exception as e:
        print(f"[major-indices poller] fetch error: {e}")
    return False


def _fetch_and_cache_breadth():
    """抓取沪深涨跌家数并写入缓存"""
    try:
        url = "https://push2delay.eastmoney.com/api/qt/ulist.np/get"
        params = {'fltt': 2, 'invt': 2, 'fields': 'f104,f105', 'secids': '1.000001,0.399001', 'ut': _EM_UT}
        r = requests.get(url, params=params, headers=_EM_HEADERS, timeout=8, proxies=REQUEST_PROXIES)
        diff = (r.json().get('data') or {}).get('diff') or []
        rise = sum(int(row.get('f104', 0)) for row in diff)
        fall = sum(int(row.get('f105', 0)) for row in diff)
        _cache[_MARKET_BREADTH_KEY] = ((rise, fall), time.time())
        return True
    except Exception as e:
        print(f"[breadth poller] fetch error: {e}")
    return False


def _fetch_and_cache_sh_minute():
    """抓取上证分时走势并写入缓存"""
    try:
        url = "https://push2delay.eastmoney.com/api/qt/stock/trends2/get?secid=1.000001&fields1=f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13&fields2=f51,f52,f53,f54,f55,f56,f57,f58&ndays=1"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36', 'Accept': '*/*', 'Referer': 'https://www.eastmoney.com/'}
        r = requests.get(url, headers=headers, timeout=10, proxies=REQUEST_PROXIES)
        data = r.json()
        if data.get('rc') == 0 and data.get('data'):
            sd = data['data']
            trends = sd.get('trends', [])
            pre_close = sd.get('preClose', 0)
            times, prices = [], []
            for trend in trends:
                parts = trend.split(',')
                if len(parts) >= 2:
                    time_str = parts[0].split(' ')[-1] if ' ' in parts[0] else parts[0]
                    if time_str < '09:30':
                        continue
                    times.append(time_str)
                    prices.append(float(parts[1]))
            cp = prices[-1] if prices else pre_close
            cv = cp - pre_close if pre_close else 0
            cpt = (cv / pre_close * 100) if pre_close else 0
            result = {
                'success': True,
                'data': {
                    'name': sd.get('name', '上证指数'),
                    'preClose': pre_close,
                    'currentPrice': cp,
                    'change': f"{'+' if cpt >= 0 else ''}{cpt:.2f}%",
                    'changeValue': f"{'+' if cv >= 0 else ''}{cv:.2f}",
                    'times': times, 'prices': prices,
                }
            }
            _cache[_SH_MINUTE_KEY] = (result, time.time())
            return True
    except Exception as e:
        print(f"[sh-minute poller] fetch error: {e}")
    return False


def _fetch_and_cache_daily_closes():
    """抓取沪深指数30天日K收盘价并写入缓存（使用腾讯接口）"""
    try:
        result = {}
        for symbol in ['sh000001', 'sz399001']:
            param_val = f"{symbol},day,,,30,qfq"
            r = requests.get("https://web.ifzq.gtimg.cn/appstock/app/fqkline/get",
                params={'param': param_val},
                headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://finance.qq.com/'},
                timeout=10, proxies=REQUEST_PROXIES,
            )
            jd = r.json()
            jd_data = (jd.get('data') or {}).get(symbol, {})
            day_rows = jd_data.get('day') or jd_data.get('qfqday') or []
            closes = [float(row[2]) for row in day_rows if len(row) >= 3]
            result[symbol] = closes
        _cache[_DAILY_CLOSES_KEY] = (result, datetime.date.today().strftime('%Y-%m-%d'))
        return True
    except Exception as e:
        print(f"[daily-closes poller] fetch error: {e}")
    return False


def get_major_indices():
    """上证指数实时行情（从缓存读取）"""
    if _MAJOR_INDICES_KEY in _cache:
        return _cache[_MAJOR_INDICES_KEY][0]
    return {'success': False, 'error': '暂无指数数据'}


def get_sh000001_minute_data():
    """上证指数分时走势（从缓存读取）"""
    cached = _cache.get(_SH_MINUTE_KEY)
    if cached:
        return cached[0]
    return {'success': False, 'error': '暂无分时数据'}


def get_index_minute_data():
    """成交额分时数据（从缓存读取）"""
    cached = _cache.get(_TURNOVER_MINUTE_KEY)
    if cached:
        return cached[0]
    return {'success': False, 'error': '暂无成交额数据'}
