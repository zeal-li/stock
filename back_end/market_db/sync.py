"""全市场数据同步 — 启动时增量更新已有股票，K 线按需分段拉取"""
import datetime
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from market_db.db import stock_count, stocks_save, stocks_append, stocks_all, kline_latest_date, klines_insert

# 市场分段定义
SEGMENTS = {
    'sh_main':    {'label': '沪市主板', 'prefix': ('600', '601', '603', '605')},
    'sz_main':    {'label': '深市主板', 'prefix': ('000', '001', '002', '003')},
    'gem':        {'label': '创业板',   'prefix': ('300', '301')},
    'star':       {'label': '科创板',   'prefix': ('688',)},
    'sz_etf':     {'label': '深市ETF',  'prefix': ('159', '16')},
    'sh_etf':     {'label': '沪市ETF',  'prefix': ('51',)},
}


def _fetch_stock_list(prefix=None):
    """从 akshare 获取股票列表，可选按代码前缀过滤。返回 [(code, market, name), ...]"""
    import akshare as ak
    try:
        all_prefixes = ('0', '3', '6', '15', '16', '51') if prefix is None else prefix
        label = '全量' if prefix is None else ','.join(prefix)
        is_etf = any(p.startswith(('15', '16', '51')) for p in (prefix or ()))

        if is_etf and prefix:
            df_etf = ak.fund_etf_spot_em()
            print(f"[market_db] ETF 原始表头: {list(df_etf.columns)[:5]}, 行数: {len(df_etf)}")
            code_col = '代码' if '代码' in df_etf.columns else df_etf.columns[0]
            name_col = '名称' if '名称' in df_etf.columns else df_etf.columns[1]
            rows = []
            for _, row in df_etf.iterrows():
                code = str(row[code_col]).zfill(6)
                if not code.startswith(prefix): continue
                name = str(row[name_col])
                market = '0' if code.startswith(('15', '16')) else '1'
                rows.append((code, market, name))
        else:
            # 普通股票优先用 spot（活跃），失败回退到 info（全量）
            df = None
            try:
                df = ak.stock_zh_a_spot_em()
            except Exception:
                pass
            if df is None or df.empty:
                df = ak.stock_info_a_code_name()
            if df is None or df.empty:
                print("[market_db] akshare 返回空列表")
                return []
            rows = []
            for _, row in df.iterrows():
                code = str(row.get('代码', row.get('code', ''))).zfill(6)
                if not code.startswith(all_prefixes): continue
                name = str(row.get('名称', row.get('name', '')))
                if code.startswith(('15', '16')): market = '0'
                elif code.startswith('51'): market = '1'
                elif code.startswith(('6',)): market = '1'
                else: market = '0'
                rows.append((code, market, name))
        print(f"[market_db] 股票列表({label})：找到 {len(rows)} 只")
        if rows and prefix is None:
            stocks_save(rows)
        elif rows:
            stocks_append(rows)
        return rows
    except Exception as e:
        print(f"[market_db] 股票列表获取失败: {e}")
        return []


def _fetch_kline(code, market, period, start_date, end_date):
    """从 akshare 获取单只股票 K 线"""
    import akshare as ak
    for attempt in range(3):
        try:
            df = ak.stock_zh_a_hist(symbol=code, period=period,
                                    start_date=start_date, end_date=end_date, adjust="qfq")
            if df is None or df.empty:
                return []
            rows = []
            for _, row in df.iterrows():
                rows.append((
                    code, market, period,
                    str(row['日期'])[:10],
                    float(row['开盘']), float(row['最高']), float(row['最低']),
                    float(row['收盘']), float(row['成交量']), float(row['成交额'])
                ))
            return rows
        except Exception:
            if attempt < 2:
                time.sleep(2 * (attempt + 1))
    return []


def _sync_one_stock(code, market, periods=('daily',)):
    """增量同步单只股票 K 线（只拉缺失日期）"""
    today = datetime.date.today()
    for period in periods:
        latest = kline_latest_date(code, market, period)
        if latest:
            last_date = datetime.date.fromisoformat(latest)
            if last_date >= today:
                continue
            start = (last_date + datetime.timedelta(days=1)).strftime('%Y%m%d')
        else:
            # 数据库里没有这只股票的 K 线 → 全量拉
            start = '19900101'
        end = today.strftime('%Y%m%d')
        rows = _fetch_kline(code, market, period, start, end)
        if rows:
            klines_insert(rows)


# ---- 启动时增量同步线程 ----

def _startup_sync_worker():
    """启动时遍历已有股票，增量更新日K/周K/月K"""
    stocks = stocks_all()
    if not stocks:
        print("[market_db] 股票列表为空，跳过增量同步")
        return

    # 0. 清理退市股票：直接调东方财富 API 获取活跃列表
    try:
        import requests as _rq
        active_set = set()
        # A股活跃列表
        url = 'https://push2.eastmoney.com/api/qt/clist/get'
        params = {
            'pn': 1, 'pz': 6000, 'po': 1, 'np': 1,
            'fltt': 2, 'invt': 2,
            'fid': 'f3', 'fs': 'm:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23',
            'fields': 'f12',
            'ut': 'bd1d9ddb04089700cf9c27f6f7426281',
        }
        headers = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://quote.eastmoney.com/'}
        r = _rq.get(url, params=params, headers=headers, timeout=30)
        data = r.json()
        for item in (data.get('data') or {}).get('diff') or []:
            active_set.add(str(item['f12']).zfill(6))
        # ETF活跃列表
        params['fs'] = 'b:MK0021,b:MK0022,b:MK0023,b:MK0024'
        r = _rq.get(url, params=params, headers=headers, timeout=30)
        data = r.json()
        for item in (data.get('data') or {}).get('diff') or []:
            active_set.add(str(item['f12']).zfill(6))
        if active_set:
            delisted = [s for s in stocks if s[0] not in active_set]
            if delisted:
                from market_db.db import stocks_remove
                for code, market, _ in delisted:
                    stocks_remove(code, market)
                print(f"[market_db] 清理退市股票：{len(delisted)} 只")
                stocks = stocks_all()
    except Exception as e:
        print(f"[market_db] 退市检查失败：{e}")

    today = datetime.date.today().strftime('%Y-%m-%d')
    print(f"[market_db] 开始增量更新（{len(stocks)} 只，目标日期 {today}）...")
    t0 = time.time()

    # 检查是否有需要更新的股票
    need_update = []
    for code, market, _ in stocks:
        latest = kline_latest_date(code, market, 'daily')
        if not latest or latest < today:
            need_update.append((code, market))

    if not need_update:
        print(f"[market_db] 所有股票数据已是最新，跳过\n")
        return

    print(f"[market_db] {len(need_update)}/{len(stocks)} 只需更新")
    total = len(need_update)

    def _progress(done, total, label, t_start):
        pct = done / total * 100
        bar_len = 30
        filled = int(bar_len * done / total)
        bar = '█' * filled + '░' * (bar_len - filled)
        elapsed = time.time() - t_start
        eta = elapsed / done * (total - done) if done > 0 else 0
        print(f"\r[market_db] {label} [{bar}] {pct:5.1f}% {done}/{total}  已耗时 {elapsed:.0f}s 预计剩余 {eta:.0f}s", end='', flush=True)

    done = 0
    _progress(0, total, '日K增量  ', t0)
    with ThreadPoolExecutor(max_workers=4) as pool:
        futs = {pool.submit(_sync_one_stock, s[0], s[1], ('daily',)): s for s in need_update}
        for fut in as_completed(futs):
            try:
                fut.result()
            except Exception:
                pass
            done += 1
            _progress(done, total, '日K增量  ', t0)
    print()

    # 周K/月K
    t1 = time.time()
    done = 0
    _progress(0, total, '周月K增量', t1)
    with ThreadPoolExecutor(max_workers=4) as pool:
        futs = {pool.submit(_sync_one_stock, s[0], s[1], ('weekly', 'monthly')): s for s in need_update}
        for fut in as_completed(futs):
            try:
                fut.result()
            except Exception:
                pass
            done += 1
            _progress(done, total, '周月K增量', t1)
    print()

    elapsed = time.time() - t0
    print(f"[market_db] 增量更新完成，耗时 {elapsed:.0f}s（{len(need_update)} 只）\n")


def init_stock_list():
    """启动时初始化股票列表（仅列表，不同步 K 线）"""
    if stock_count() == 0:
        n = _fetch_stock_list()
        print(f"[market_db] 首次初始化股票列表：{n} 只")
    else:
        n = stock_count()
        print(f"[market_db] 股票列表就绪：{n} 只")


def start_startup_sync():
    """启动时增量更新已有股票的 K 线（后台线程）"""
    t = threading.Thread(target=_startup_sync_worker, daemon=True, name='market-db-startup')
    t.start()


# ---- 按市场分段同步 K 线 ----

_sync_state = {'running': False, 'label': '', 'total': 0, 'done': 0, 'errors': 0}


def _run_segment_sync(seg_key):
    """后台执行一个市场分段的同步"""
    seg = SEGMENTS[seg_key]
    prefix = seg['prefix']
    stocks = [s for s in stocks_all() if s[0].startswith(prefix)]
    if not stocks:
        # 该分段还没拉过，先拉取股票列表并追加
        _fetch_stock_list(prefix)
        stocks = [s for s in stocks_all() if s[0].startswith(prefix)]
    if not stocks:
        _sync_state.update({'running': False, 'done': 0, 'total': 0, 'errors': 0})
        return

    _sync_state.update({'running': True, 'label': seg['label'], 'total': len(stocks), 'done': 0, 'errors': 0})

    def _mark_progress(d, t, label, start_time):
        p = d / t * 100 if t else 0
        bar = '█' * int(30 * d / t) + '░' * (30 - int(30 * d / t)) if t else ''
        el = time.time() - start_time
        et = el / d * (t - d) if d > 0 else 0
        print(f"\r[market_db] {seg['label']} {label} [{bar}] {p:5.1f}% {d}/{t}  {el:.0f}s/{et:.0f}s", end='', flush=True)

    total = len(stocks)
    t0 = time.time()
    done = 0
    _mark_progress(0, total, '日K ', t0)
    with ThreadPoolExecutor(max_workers=4) as pool:
        futs = {pool.submit(_sync_one_stock, s[0], s[1], ('daily',)): s for s in stocks}
        for fut in as_completed(futs):
            try: fut.result()
            except Exception: _sync_state['errors'] += 1
            done += 1
            _sync_state['done'] = done
            _mark_progress(done, total, '日K ', t0)
    print()

    t1 = time.time()
    done = 0
    _sync_state['done'] = 0
    _mark_progress(0, total, '周月K', t1)
    with ThreadPoolExecutor(max_workers=4) as pool:
        futs = {pool.submit(_sync_one_stock, s[0], s[1], ('weekly', 'monthly')): s for s in stocks}
        for fut in as_completed(futs):
            try: fut.result()
            except Exception: _sync_state['errors'] += 1
            done += 1
            _sync_state['done'] = done + total
            _mark_progress(done, total, '周月K', t1)
    print()

    _sync_state['running'] = False


def start_segment_sync(seg_key):
    """由 API 调用：启动指定市场分段的同步"""
    if seg_key not in SEGMENTS:
        return False
    if _sync_state['running']:
        return False
    t = threading.Thread(target=_run_segment_sync, args=(seg_key,), daemon=True)
    t.start()
    return True


def get_sync_status():
    """查询同步进度"""
    return dict(_sync_state)
