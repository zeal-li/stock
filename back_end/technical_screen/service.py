"""技术选股 — 基于 stock_detail_list.db 的 K 线缓存扫描"""
import os, json, threading, sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed

from .strategies.ascending_channel import calc as ascending_channel_calc


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
    score, detail = ascending_channel_calc(klines)
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
    if not market:
        return {'success': False, 'error': '请先选择市场'}
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
        rows = conn.execute('SELECT code, name FROM stocks WHERE market=? ORDER BY code', (market,)).fetchall()
        conn.close()
        stocks = [(r['code'], r['name']) for r in rows]

        conn2 = _kline_conn()
        has_kline = set(r['code'] for r in
            conn2.execute('SELECT DISTINCT code FROM klines WHERE period="daily" AND market=?', (market,)).fetchall())
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
