"""技术选股 — 基于 stock_detail_list.db 的 K 线缓存扫描"""
import os, json, threading, sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed


def _kline_conn():
    import sqlite3
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'stock_detail_list.db')
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _list_conn():
    import sqlite3
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'stock_list.db')
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _calc_ascending_channel(klines, lookback=60):
    """上升通道检测"""
    if len(klines) < lookback:
        return 0, {}
    window = klines[-lookback:]
    highs = [k['high'] for k in window]
    lows = [k['low'] for k in window]
    closes = [k['close'] for k in window]
    volumes = [k['volume'] for k in window]
    def _lr(y):
        n = len(y); x = list(range(n))
        sx = sum(x); sy = sum(y)
        sxy = sum(x[i]*y[i] for i in range(n))
        sx2 = sum(v**2 for v in x)
        d = n*sx2 - sx*sx
        if d == 0: return 0, 0, 0
        sl = (n*sxy - sx*sy) / d
        ic = (sy - sl*sx) / n
        ym = sy / n
        ssr = sum((y[i] - (sl*x[i] + ic))**2 for i in range(n))
        sst = sum((v - ym)**2 for v in y)
        r2 = 1 - ssr / sst if sst > 0 else 0
        return sl, ic, r2
    hs, hi, hr = _lr(highs)
    ls, li, lr = _lr(lows)
    if hs <= 0 or ls <= 0 or hr < 0.6 or lr < 0.6 or hs > ls * 3:
        return 0, {}
    idx = lookback - 1
    upper = hs * idx + hi
    lower = ls * idx + li
    cur = closes[-1]
    cw = upper - lower
    if cw <= 0 or cw / lower > 0.30:
        return 0, {}
    pos = (cur - lower) / cw
    if pos < 0.2 or pos > 0.9:
        return 0, {}
    v5 = sum(volumes[-5:]) / 5 if len(volumes) >= 5 else 0
    v20 = sum(volumes[-20:]) / 20 if len(volumes) >= 20 else v5
    if v20 > 0 and v5 / v20 < 0.8:
        return 0, {}
    score = round(hr*30 + lr*30 + (1-abs(pos-0.5)*2)*20 + min(v5/v20*10, 10 if v20>0 else 0) + min(hs/(lower/100)*5, 10), 1)
    return score, {'upper': round(upper,2), 'lower': round(lower,2),
                   'hi_slope': round(hs,4), 'lo_slope': round(ls,4),
                   'hi_r2': round(hr,2), 'lo_r2': round(lr,2),
                   'pos': round(pos*100,1), 'channel_width_pct': round(cw/lower*100,1),
                   'vol_ratio': round(v5/v20,2) if v20>0 else 1}


def _scan_one(code, name):
    """扫描单只股票"""
    conn = _kline_conn()
    rows = conn.execute(
        'SELECT date, open, high, low, close, volume FROM klines '
        'WHERE code=? AND period=? ORDER BY date DESC LIMIT 120',
        (code, 'daily')).fetchall()
    conn.close()
    if not rows:
        return None
    klines = [dict(r) for r in reversed(rows)]
    score, detail = _calc_ascending_channel(klines)
    if score <= 0:
        return None
    return {
        'code': code, 'name': name if name else code,
        'price': f"{klines[-1]['close']:.2f}",
        'score': score, 'detail': detail,
    }


# ---- 异步扫描 ----

_scan_state = {'running': False, 'total': 0, 'done': 0, 'results': []}


def run_ascending_channel_async(market=None, max_workers=30):
    if _scan_state['running']:
        return {'success': False, 'error': '扫描进行中'}
    _scan_state['running'] = True
    _scan_state['done'] = 0
    _scan_state['results'] = []
    import threading
    threading.Thread(target=_do_scan, args=(market, max_workers), daemon=True).start()
    return {'success': True, 'message': '扫描已启动'}


def get_scan_status():
    return {
        'running': _scan_state['running'],
        'total': _scan_state['total'],
        'done': _scan_state['done'],
        'results': sorted(_scan_state['results'], key=lambda x: x['score'], reverse=True),
    }


def _do_scan(market, max_workers):
    global _scan_state
    try:
        conn = _list_conn()
        if market:
            rows = conn.execute('SELECT code, name FROM stocks WHERE market=? ORDER BY code', (market,)).fetchall()
        else:
            rows = conn.execute('SELECT code, name FROM stocks ORDER BY code').fetchall()
        conn.close()
        stocks = [(r['code'], r['name']) for r in rows]

        # 只扫描 stock_detail_list.db 里有 K 线数据的
        conn2 = _kline_conn()
        if market:
            has_kline = set(r['code'] for r in
                conn2.execute('SELECT DISTINCT code FROM klines WHERE period="daily" AND market=?', (market,)).fetchall())
        else:
            has_kline = set(r['code'] for r in
                conn2.execute('SELECT DISTINCT code FROM klines WHERE period="daily"').fetchall())
        conn2.close()
        scan_list = [(c, n) for c, n in stocks if c in has_kline]

        _scan_state['total'] = len(scan_list)
        results = []
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(_scan_one, c, n): c for c, n in scan_list}
            for future in as_completed(futures):
                try:
                    r = future.result()
                    if r: results.append(r)
                except Exception:
                    pass
                _scan_state['done'] += 1
                _scan_state['results'] = list(results)
        _scan_state['results'] = list(results)
    finally:
        _scan_state['running'] = False
