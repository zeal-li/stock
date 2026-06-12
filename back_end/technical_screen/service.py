"""技术选股 — 基于 stock_detail_list.db 的 K 线缓存扫描"""
import os, json, threading, sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed

from .strategies.san_shang_score import calc as prediction_calc
from .strategies.san_shang_you_ya import calc as san_shang_you_ya_calc

# 策略注册表：{key: {name, calc, desc}}
STRATEGIES = {
    'san_shang_you_ya': {
        'name': '三上悠亚',
        'calc': san_shang_you_ya_calc,
        'desc': '日K/周K/月K布林中上轨共振：三周期大部分时间运行在中轨到上轨之间，布林带温和向上倾斜，跌破中轨能快速修复视为强势，近期无极端涨跌',
    },
}


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


def _scan_one(code, name, strategy_key):
    """扫描单只股票"""
    strategy = STRATEGIES.get(strategy_key)
    if not strategy:
        return None
    conn = _kline_conn()
    daily_rows = conn.execute(
        'SELECT date, open, high, low, close, volume FROM klines '
        'WHERE code=? AND period=? ORDER BY date DESC LIMIT 120',
        (code, 'daily')).fetchall()
    weekly_rows = conn.execute(
        'SELECT date, open, high, low, close, volume FROM klines '
        'WHERE code=? AND period=? ORDER BY date DESC LIMIT 60',
        (code, 'weekly')).fetchall()
    monthly_rows = conn.execute(
        'SELECT date, open, high, low, close, volume FROM klines '
        'WHERE code=? AND period=? ORDER BY date DESC LIMIT 36',
        (code, 'monthly')).fetchall()
    conn.close()
    if not daily_rows:
        return None
    klines = [dict(r) for r in reversed(daily_rows)]
    weekly_klines = [dict(r) for r in reversed(weekly_rows)]
    monthly_klines = [dict(r) for r in reversed(monthly_rows)]
    score, detail = strategy['calc'](klines, weekly_klines=weekly_klines, monthly_klines=monthly_klines)
    if score <= 0:
        return None
    return {
        'code': code, 'name': name if name else code,
        'price': f"{klines[-1]['close']:.2f}",
        'score': score, 'detail': detail,
    }


# ---- 异步扫描 ----

_scan_state = {'running': False, 'total': 0, 'done': 0, 'results': []}


def get_strategies():
    """返回可用策略列表"""
    return [{'key': k, 'name': v['name'], 'desc': v['desc']} for k, v in STRATEGIES.items()]


def run_scan_async(strategy_keys, market=None, max_workers=30):
    """启动异步扫描，支持多个策略 pipeline 串联筛选"""
    if isinstance(strategy_keys, str):
        strategy_keys = [strategy_keys]
    for sk in strategy_keys:
        if sk not in STRATEGIES:
            return {'success': False, 'error': f'无效的策略: {sk}'}
    if not market:
        return {'success': False, 'error': '请先选择市场'}
    if _scan_state['running']:
        return {'success': False, 'error': '扫描进行中'}
    _scan_state['running'] = True
    _scan_state['done'] = 0
    _scan_state['total'] = 0
    _scan_state['results'] = []
    import threading
    threading.Thread(target=_do_scan, args=(strategy_keys, market, max_workers), daemon=True).start()
    return {'success': True, 'message': '扫描已启动'}






def get_scan_status():
    return {
        'running': _scan_state['running'],
        'total': _scan_state['total'],
        'done': _scan_state['done'],
        'results': sorted(_scan_state['results'], key=lambda x: x['score'], reverse=True),
    }


def _batch_scan(stocks, strategy_key, market, max_workers, done_offset=0):
    """对一批股票执行单策略扫描，返回命中的结果列表，更新 done 进度"""
    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_scan_one, c, n, strategy_key): c for c, n in stocks}
        for future in as_completed(futures):
            try:
                r = future.result()
                if r:
                    r['market'] = market
                    results.append(r)
            except Exception:
                pass
            _scan_state['done'] += 1
            _scan_state['results'] = list(results)
    return results


def _do_scan(strategy_keys, market, max_workers):
    global _scan_state
    try:
        conn = _list_conn()
        rows = conn.execute('SELECT code, name FROM stocks WHERE market=? ORDER BY code', (market,)).fetchall()
        conn.close()
        all_stocks = [(r['code'], r['name']) for r in rows]

        conn2 = _kline_conn()
        has_kline = set(r['code'] for r in
            conn2.execute('SELECT DISTINCT code FROM klines WHERE period="daily" AND market=?', (market,)).fetchall())
        conn2.close()
        scan_list = [(c, n) for c, n in all_stocks if c in has_kline]

        # pipeline 串联筛选：第一个策略扫全量，后续策略只扫上一轮命中的
        results = []
        for i, strategy_key in enumerate(strategy_keys):
            if i == 0:
                candidates = scan_list
            else:
                if not results:
                    break
                candidates = [(r['code'], None) for r in results]
                results = []

            # 本阶段开始前更新 total（累加本阶段要扫的数量）
            _scan_state['total'] += len(candidates)
            results = _batch_scan(candidates, strategy_key, market, max_workers)

        # ---- 对最终筛选结果计算预测评分 ----
        if results:
            pred_total = len(results)
            for idx, r in enumerate(results):
                try:
                    conn = _kline_conn()
                    rows = conn.execute(
                        'SELECT date, open, high, low, close, volume FROM klines '
                        'WHERE code=? AND period=? ORDER BY date DESC LIMIT 120',
                        (r['code'], 'daily')).fetchall()
                    conn.close()
                    if rows:
                        klines = [dict(row) for row in reversed(rows)]
                        pred = prediction_calc(klines)
                        r['prediction'] = pred
                except Exception:
                    r['prediction'] = {'direction': 'bullish', 'score': 0, 'detail': {}}
                # 阶段性更新中间结果，让前端看到预测评分逐步出现
                if idx % 5 == 0 or idx == pred_total - 1:
                    _scan_state['results'] = list(results)

        _scan_state['results'] = list(results)
    finally:
        _scan_state['running'] = False
