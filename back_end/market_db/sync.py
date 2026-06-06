"""全市场数据同步
启动时：
  1. 刷新 stock_list.db：按 segment 拉取在市的股票列表（有日期判断，同日不重复拉）
  2. 同步 stock_detail_list.db：遍历已有股票，缺数据全量拉/有数据增量拉
  3. 清理：detail 里 list 里没有的股票 → 退市，删除
"""
import datetime
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from .db import (
    list_markets, list_replace_market, list_sync_date_get, list_sync_date_set,
    list_stocks_all,
    detail_info_all, detail_info_get, detail_info_upsert,
    detail_klines_insert, detail_remove_stock,
)

# 市场分段 — key 用作 market 字段值
SEGMENTS = {
    'sh_main': {'label': '沪A',   'prefix': ('600', '601', '603', '605')},
    'sz_main': {'label': '深A',   'prefix': ('000', '001', '002', '003')},
    'sh_etf':  {'label': '沪ETF',  'prefix': ('5',)},
    'sz_etf':  {'label': '深ETF',  'prefix': ('159', '16', '18')},
    'gem':     {'label': '创业板', 'prefix': ('300', '301')},
    'star':    {'label': '科创板', 'prefix': ('688',)},
    'bj':      {'label': '北交所', 'prefix': ('83', '87', '88')},
    'xsb':     {'label': '新三板', 'prefix': ('43',)},
}


def _today_str():
    return datetime.date.today().strftime('%Y-%m-%d')


def _code_to_segment(code):
    """代码 → segment key"""
    for key, seg in SEGMENTS.items():
        for p in seg['prefix']:
            if code.startswith(p):
                return key
    return None


# =========== 步骤 1：刷新股票列表 ===========

def _fetch_stocks_by_segment(seg_key):
    """只拉取指定分段的市场股票列表"""
    import requests
    import time as _time

    seg = SEGMENTS[seg_key]
    label = seg['label']
    url = 'https://push2delay.eastmoney.com/api/qt/clist/get'
    headers = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://data.eastmoney.com/'}

    # 根据分段选 fs 过滤器
    if seg_key in ('sh_main', 'sz_main', 'gem', 'star'):
        fs_filter = 'm:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23'
    elif seg_key in ('sz_etf', 'sh_etf'):
        fs_filter = 'b:MK0021,b:MK0022,b:MK0023,b:MK0024'
    else:
        print(f"[sync] {label} 暂不支持（API 无此市场数据）")
        return []

    all_rows = []
    page = 1
    print(f"[sync] 拉取 {label} 列表...")
    while True:
        r = None
        for attempt in range(3):
            try:
                r = requests.get(url, params={
                    'pn': page, 'pz': 1000, 'po': 1, 'np': 1,
                    'fltt': 2, 'invt': 2,
                    'fid': 'f12',
                    'fs': fs_filter,
                    'fields': 'f2,f12,f14',
                    'ut': 'bd1d9ddb04089700cf9c27f6f7426281',
                }, headers=headers, timeout=15)
                break
            except Exception:
                if attempt < 2: _time.sleep(2 * (attempt + 1))
        if r is None:
            print(f"[sync] {label} 第{page}页请求失败（已重试3次）")
            break
        data = r.json().get('data') or {}
        diff = data.get('diff') or {}
        items = diff.values() if isinstance(diff, dict) else (diff if isinstance(diff, list) else [])
        if not items:
            break
        for row in items:
            code = str(row.get('f12', '')).zfill(6)
            name = str(row.get('f14', ''))
            if len(code) != 6 or not code.isdigit():
                continue
            seg = _code_to_segment(code)
            if seg != seg_key:
                continue
            if seg_key in ('sz_etf', 'sh_etf'):
                if not any(code.startswith(p) for p in SEGMENTS[seg_key]['prefix']):
                    continue
            all_rows.append((code, name))
        page += 1
        _time.sleep(0.1)
    print(f"[sync] {label}: {len(all_rows)} 只")
    return all_rows


def _fetch_active_stocks():
    """拉取全市场（用于增量刷新已有分段）"""
    all_rows = []
    for seg_key in SEGMENTS:
        rows = _fetch_stocks_by_segment(seg_key)
        for code, name in rows:
            all_rows.append((code, seg_key, name))
    return all_rows


def _refresh_stock_list():
    """刷新 stock_list.db：只更新已存在的 segment"""
    today = _today_str()
    markets = list_markets()

    if not markets:
        print("[sync] stock_list.db 为空，跳过列表刷新")
        return

    all_synced = all(list_sync_date_get(m) == today for m in markets)
    if all_synced:
        print("[sync] 股票列表已是最新（今日已更新），跳过")
        return

    print("[sync] 获取在市的股票列表...")
    all_rows = _fetch_active_stocks()
    if all_rows is None:
        print("[sync] 获取失败，保留现有列表")
        return

    by_market = {}
    for code, seg, name in all_rows:
        by_market.setdefault(seg, []).append((code, name))

    for m in markets:
        rows = by_market.get(m, [])
        list_replace_market(m, rows)
        print(f"[sync] {SEGMENTS.get(m, {}).get('label', m)} 列表已更新: {len(rows)} 只")


# =========== 步骤 2：同步 K 线 ===========

def _fetch_kline(code, seg_key, period, start_date, end_date):
    """从腾讯 API 获取 K 线（前复权，按条数拉取）"""
    import requests as _rq
    c = str(code)
    pfx = 'sh' if c.startswith(('6', '9')) else 'sz'
    tp_map = {'daily': ('day', 800), 'weekly': ('week', 200), 'monthly': ('month', 40)}
    tp, count = tp_map.get(period, ('day', 800))
    for attempt in range(3):
        try:
            r = _rq.get(
                "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get",
                params={'param': f"{pfx}{c},{tp},,,{count},qfq"},
                headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://finance.qq.com/'},
                timeout=10,
            )
            jd = r.json()
            data = jd.get('data', {})
            if isinstance(data, dict):
                sd = data.get(f"{pfx}{c}", {})
            else:
                return []
            if tp == 'day':
                raw = sd.get('day') or sd.get('qfqday') or []
            elif tp == 'week':
                raw = sd.get('qfqweek') or sd.get('week') or []
            else:
                raw = sd.get('qfqmonth') or sd.get('month') or []
            if not raw:
                return []
            rows = []
            for row in raw:
                if len(row) < 6:
                    continue
                date_str = str(row[0])[:10].replace('-', '')
                # 按日期范围过滤
                if start_date and date_str < start_date:
                    continue
                if end_date and date_str > end_date:
                    continue
                rows.append((
                    code, seg_key, period,
                    date_str,
                    float(row[1]), float(row[3]), float(row[4]),
                    float(row[2]), float(row[5]),
                    float(row[6]) if len(row) >= 7 else 0,
                ))
            return rows
        except Exception:
            if attempt < 2:
                time.sleep(2 * (attempt + 1))
    return []


def _sync_one_stock(code, market, name, periods=('daily', 'weekly', 'monthly')):
    """同步单只股票所有周期的 K 线"""
    today = _today_str()
    info = detail_info_get(code, market)
    max_date = info['latest_kline_date'] if info else None

    if max_date and max_date >= today:
        return

    all_rows = []
    for period in periods:
        if max_date and max_date != '':
            last = datetime.date.fromisoformat(max_date)
            start = (last + datetime.timedelta(days=1)).strftime('%Y%m%d')
        else:
            start = '19900101'
        end = today.replace('-', '')
        rows = _fetch_kline(code, market, period, start, end)
        for r in rows:
            all_rows.append(r)

    if all_rows:
        detail_klines_insert(all_rows)
        latest = max(r[3] for r in all_rows)
    else:
        latest = max_date or ''

    detail_info_upsert(code, market, name or code, latest)


def _sync_klines():
    """遍历 stock_list.db，增量同步 K 线"""
    global _sync_status
    stocks = list_stocks_all()
    if not stocks:
        print("[sync] 股票列表为空，跳过 K 线同步")
        _sync_status['running'] = False
        return

    total = len(stocks)
    _sync_status['total'] = total
    _sync_status['done'] = 0
    _sync_status['phase'] = 'kline'
    print(f"[sync] 开始同步 K 线 ({total} 只，4 线程增量)...")

    t0 = time.time()

    with ThreadPoolExecutor(max_workers=4) as pool:
        futs = {pool.submit(_sync_one_stock, s[0], s[1], s[2]): s for s in stocks}
        for fut in as_completed(futs):
            try:
                fut.result()
            except Exception:
                pass
            _sync_status['done'] += 1
            step = 10
            if _sync_status['done'] % step == 0 or _sync_status['done'] == total:
                pct = _sync_status['done'] / total * 100
                el = time.time() - t0
                eta = el / _sync_status['done'] * (total - _sync_status['done']) if _sync_status['done'] > 0 else 0
                bar = '█' * int(30 * _sync_status['done'] / total) + '░' * (30 - int(30 * _sync_status['done'] / total))
                print(f"\r[sync] K线 [{bar}] {pct:5.1f}% {_sync_status['done']}/{total}  耗时 {el:.0f}s 预计剩余 {eta:.0f}s", end='', flush=True)
    print()
    print(f"[sync] K 线同步完成，耗时 {time.time()-t0:.0f}s")


# =========== 步骤 3：清理退市 ===========

def _cleanup_delisted():
    active = set((s[0], s[1]) for s in list_stocks_all())
    if not active:
        return

    detail_stocks = detail_info_all()
    delisted = [(s[0], s[1]) for s in detail_stocks if (s[0], s[1]) not in active]
    if not delisted:
        print("[sync] 无退市股票")
        return

    for code, market in delisted:
        detail_remove_stock(code, market)
    print(f"[sync] 清理退市股票: {len(delisted)} 只")


# =========== 初始化新市场 ===========

_sync_status = {'running': False, 'label': '', 'total': 0, 'done': 0, 'phase': ''}

def init_segment(seg_key):
    """初始化一个市场分段：拉取股票列表 + 全量同步 K 线"""
    global _sync_status
    if seg_key not in SEGMENTS:
        return {'success': False, 'error': '无效的市场分段'}

    if seg_key in list_markets():
        print(f"[sync] {SEGMENTS[seg_key]['label']} 已存在，跳过初始化")
        return {'success': False, 'error': '市场已存在'}

    if _sync_status['running']:
        return {'success': False, 'error': '已有同步任务运行中'}

    _sync_status['running'] = True
    _sync_status['label'] = SEGMENTS[seg_key]['label']
    threading.Thread(target=_run_init, args=(seg_key,), daemon=True).start()
    return {'success': True, 'message': '初始化已启动'}

def _run_init(seg_key):
    global _sync_status
    try:
        label = SEGMENTS[seg_key]['label']
        _sync_status['phase'] = 'list'
        print(f"[sync] 初始化: {label}")

        rows = _fetch_stocks_by_segment(seg_key)
        if not rows:
            _sync_status['running'] = False
            return

        list_replace_market(seg_key, rows)
        print(f"[sync] {label} 股票列表已写入: {len(rows)} 只")

        stocks = [(c, seg_key, n) for c, n in rows]
        _sync_status['total'] = len(stocks)
        _sync_status['done'] = 0
        _sync_status['phase'] = 'kline'
        print(f"[sync] 开始全量同步 K 线 ({len(stocks)} 只，4 线程)...")

        t0 = time.time()
        with ThreadPoolExecutor(max_workers=4) as pool:
            futs = {pool.submit(_sync_one_stock, s[0], s[1], s[2]): s for s in stocks}
            for fut in as_completed(futs):
                try:
                    fut.result()
                except Exception:
                    pass
                _sync_status['done'] += 1
                step = 10
                if _sync_status['done'] % step == 0 or _sync_status['done'] == len(stocks):
                    pct = _sync_status['done'] / len(stocks) * 100
                    el = time.time() - t0
                    eta = el / _sync_status['done'] * (len(stocks) - _sync_status['done']) if _sync_status['done'] > 0 else 0
                    bar = '█' * int(30 * _sync_status['done'] / len(stocks)) + '░' * (30 - int(30 * _sync_status['done'] / len(stocks)))
                    print(f"\r[sync] K线 [{bar}] {pct:5.1f}% {_sync_status['done']}/{len(stocks)}  耗时 {el:.0f}s 预计剩余 {eta:.0f}s", end='', flush=True)
        print()
        _cleanup_delisted()
        list_sync_date_set(seg_key, _today_str())
        print(f"[sync] {label} 初始化完成，耗时 {time.time()-t0:.0f}s")
    finally:
        _sync_status['running'] = False
        _sync_status['phase'] = 'done'

def get_init_status():
    return dict(_sync_status)


def get_segments_info():
    """返回各分段状态"""
    markets = list_markets()
    today = _today_str()
    result = []
    for key, seg in SEGMENTS.items():
        synced = key in markets
        fresh = list_sync_date_get(key) == today if synced else False
        count = 0
        if synced:
            conn_detail = __import__('sqlite3').connect(
                __import__('os').path.join(__import__('os').path.dirname(__import__('os').path.dirname(__file__)), 'data', 'stock_detail_list.db'))
            count = conn_detail.execute('SELECT COUNT(DISTINCT code) FROM klines WHERE market=?', (key,)).fetchone()[0]
            conn_detail.close()
        result.append({'key': key, 'label': seg['label'], 'synced': synced, 'fresh': fresh, 'kline_count': count})
    return result


# =========== 启动入口 ===========

def _startup_worker():
    """后台线程：只更新已有市场，不新增"""
    global _sync_status
    _sync_status['running'] = True
    _sync_status['label'] = '增量同步'
    print("[sync] ===== 启动增量同步 =====")
    _sync_status['phase'] = 'list'
    _refresh_stock_list()
    _sync_klines()
    _sync_status['phase'] = 'cleanup'
    _cleanup_delisted()
    # 全部完成后才更新时间戳
    today = _today_str()
    for m in list_markets():
        list_sync_date_set(m, today)
    _sync_status['running'] = False
    _sync_status['phase'] = 'done'
    print("[sync] ===== 同步完成 =====\n")


def start_startup_sync():
    t = threading.Thread(target=_startup_worker, daemon=True, name='market-sync')
    t.start()
