"""技术选股 — 上升通道本地扫描计算"""
import os, json
import requests
import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from common import REQUEST_PROXIES

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
TX_HEADERS = {'User-Agent': UA, 'Referer': 'https://finance.qq.com/'}


def _prefix(code):
    """股票代码 → 腾讯前缀"""
    c = str(code)
    if c.startswith(('6', '9')): return 'sh'
    return 'sz'


def _fetch_kline(code):
    """获取单只股票日K线 + 名称，失败返回 None"""
    try:
        p = _prefix(code)
        r = requests.get(
            "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get",
            params={'param': f"{p}{code},day,,,120,qfq"},
            headers=TX_HEADERS, timeout=8, proxies=REQUEST_PROXIES,
        )
        jd = r.json()
        stock_data = (jd.get('data') or {}).get(f"{p}{code}", {})
        name = stock_data.get('qt', {}).get(f"{p}{code}", [None])[1] or ''
        rows = stock_data.get('day') or stock_data.get('qfqday') or []
        klines = []
        for row in rows:
            if len(row) >= 6:
                klines.append({
                    'open': float(row[1]), 'close': float(row[2]),
                    'high': float(row[3]), 'low': float(row[4]),
                    'volume': float(row[5]),
                })
        return (name, klines) if klines else None
    except Exception:
        return None


def _linear_regression(y_values):
    """对 y 做线性回归，返回 (slope, intercept, r_squared)"""
    if len(y_values) < 3:
        return 0, 0, 0
    n = len(y_values)
    x = list(range(n))
    sum_x = sum(x)
    sum_y = sum(y_values)
    sum_xy = sum(x[i] * y_values[i] for i in range(n))
    sum_x2 = sum(x[i] ** 2 for i in range(n))
    sum_y2 = sum(y ** 2 for y in y_values)
    denominator = n * sum_x2 - sum_x ** 2
    if denominator == 0:
        return 0, 0, 0
    slope = (n * sum_xy - sum_x * sum_y) / denominator
    intercept = (sum_y - slope * sum_x) / n
    y_mean = sum_y / n
    ss_res = sum((y_values[i] - (slope * x[i] + intercept)) ** 2 for i in range(n))
    ss_tot = sum((y - y_mean) ** 2 for y in y_values)
    r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else 0
    return slope, intercept, r_squared


def _calc_ascending_channel(klines, lookback=60):
    """
    上升通道检测：
    1. 取最近 lookback 根K线
    2. 对最高价序列做线性回归 → 上轨斜率/拟合度
    3. 对最低价序列做线性回归 → 下轨斜率/拟合度
    4. 条件：双轨斜率>0、R²>0.6、通道宽度合理、价格在通道内、量能配合
    返回匹配分数（越高越好），不匹配返回 0
    """
    if len(klines) < lookback:
        return 0, {}
    window = klines[-lookback:]

    highs = [k['high'] for k in window]
    lows = [k['low'] for k in window]
    closes = [k['close'] for k in window]
    volumes = [k['volume'] for k in window]

    hi_slope, hi_int, hi_r2 = _linear_regression(highs)
    lo_slope, lo_int, lo_r2 = _linear_regression(lows)

    # 条件1：双轨斜率正
    if hi_slope <= 0 or lo_slope <= 0:
        return 0, {}

    # 条件2：拟合度
    if hi_r2 < 0.6 or lo_r2 < 0.6:
        return 0, {}

    # 条件3：通道方向一致（上轨斜率不太大于下轨斜率的3倍）
    if hi_slope > lo_slope * 3:
        return 0, {}

    # 条件4：当前价格在通道内
    idx = lookback - 1
    upper = hi_slope * idx + hi_int
    lower = lo_slope * idx + lo_int
    cur = closes[-1]
    channel_width = upper - lower
    if channel_width <= 0:
        return 0, {}
    pos_in_channel = (cur - lower) / channel_width
    if pos_in_channel < 0.2 or pos_in_channel > 0.9:
        return 0, {}

    # 条件5：通道宽度不能太宽（相对价格比例 < 30%）
    if channel_width / lower > 0.30:
        return 0, {}

    # 条件6：近期量能配合（近5日平均量 > 近20日平均量的80%）
    vol5 = sum(volumes[-5:]) / 5 if len(volumes) >= 5 else 0
    vol20 = sum(volumes[-20:]) / 20 if len(volumes) >= 20 else vol5
    if vol20 > 0 and vol5 / vol20 < 0.8:
        return 0, {}

    # 综合打分
    score = hi_r2 * 30 + lo_r2 * 30
    score += (1 - abs(pos_in_channel - 0.5) * 2) * 20  # 通道中部位置加分
    score += min(vol5 / vol20 * 10, 10) if vol20 > 0 else 0
    score += min(hi_slope / (lower / 100) * 5, 10)  # 斜率力度

    return round(score, 1), {
        'upper': round(upper, 2), 'lower': round(lower, 2),
        'hi_slope': round(hi_slope, 4), 'lo_slope': round(lo_slope, 4),
        'hi_r2': round(hi_r2, 2), 'lo_r2': round(lo_r2, 2),
        'pos': round(pos_in_channel * 100, 1),
        'channel_width_pct': round(channel_width / lower * 100, 1),
        'vol_ratio': round(vol5 / vol20, 2) if vol20 > 0 else 1,
    }


def _get_stock_list():
    """获取A股股票列表：优先东财API，失败回退本地JSON"""
    # 优先：东财 clist（返回名称+价格）
    try:
        url = "https://push2.eastmoney.com/api/qt/clist/get"
        params = {
            'pn': 1, 'pz': 100, 'po': 1, 'np': 1,
            'fltt': 2, 'invt': 2,
            'fs': 'm:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23',
            'fields': 'f2,f12,f14',
            'ut': 'bd1d9ddb04089700cf9c27f6f7426281',
        }
        all_stocks = []
        page = 1
        while True:
            params['pn'] = page
            r = requests.get(url, params=params, headers={
                'User-Agent': 'Mozilla/5.0', 'Referer': 'https://data.eastmoney.com/',
            }, timeout=10, proxies=REQUEST_PROXIES)
            data = r.json().get('data') or {}
            diff = data.get('diff') or []
            if not diff: break
            for row in diff:
                if row.get('f12'):
                    all_stocks.append((row.get('f12', ''), row.get('f14', ''), row.get('f2', '')))
            if page * 100 >= data.get('total', 0): break
            page += 1
        if all_stocks:
            return all_stocks
    except Exception:
        pass

    # 回退：本地JSON（exe模式下）
    dir_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    json_path = os.path.join(dir_path, 'data', 'stock_codes.json')
    try:
        codes = json.load(open(json_path, 'r', encoding='utf-8'))
        return [(c, c, '') for c in codes]
    except Exception:
        return []


import threading
_scan_state = {'running': False, 'total': 0, 'done': 0, 'results': []}

def run_ascending_channel_async(max_workers=30):
    """异步启动扫描，立即返回"""
    if _scan_state['running']:
        return {'success': False, 'error': '扫描进行中'}
    _scan_state['running'] = True
    _scan_state['done'] = 0
    _scan_state['results'] = []
    threading.Thread(target=_do_scan, args=(max_workers,), daemon=True).start()
    return {'success': True, 'message': '扫描已启动'}

def get_scan_status():
    """获取扫描进度"""
    return {
        'running': _scan_state['running'],
        'total': _scan_state['total'],
        'done': _scan_state['done'],
        'results': sorted(_scan_state['results'], key=lambda x: x['score'], reverse=True),
    }

def _do_scan(max_workers):
    global _scan_state
    try:
        stocks = _get_stock_list()
        if not stocks:
            _scan_state['running'] = False
            return
        _scan_state['total'] = len(stocks)
        results = []
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {}
            for code, name, price in stocks:
                futures[pool.submit(_scan_one, code, name, price)] = (code, name, price)
            for future in as_completed(futures):
                try:
                    r = future.result()
                    if r:
                        results.append(r)
                except Exception:
                    pass
                _scan_state['done'] += 1
                _scan_state['results'] = list(results)
        _scan_state['results'] = list(results)
    finally:
        _scan_state['running'] = False


def _scan_one(code, name, price):
    """扫描单只股票"""
    result = _fetch_kline(code)
    if not result:
        return None
    stock_name, klines = result
    score, detail = _calc_ascending_channel(klines)
    if score <= 0:
        return None
    return {
        'code': code,
        'name': stock_name or name,
        'price': price if price else (klines[-1]['close'] if klines else ''),
        'score': score,
        'detail': detail,
    }
