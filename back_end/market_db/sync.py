"""全市场数据同步 — 启动时增量更新已有股票，K 线按需分段拉取"""
import datetime
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from market_db.db import stock_count, stocks_save, stocks_all, kline_latest_date, klines_insert

# 市场分段定义
SEGMENTS = {
    'sh_main':    {'label': '沪市主板', 'prefix': ('600', '601', '603', '605')},
    'sz_main':    {'label': '深市主板', 'prefix': ('000', '001', '002', '003')},
    'gem':        {'label': '创业板',   'prefix': ('300', '301')},
    'star':       {'label': '科创板',   'prefix': ('688',)},
    'sz_etf':     {'label': '深市ETF',  'prefix': ('159', '16')},
    'sh_etf':     {'label': '沪市ETF',  'prefix': ('51',)},
}


def _fetch_stock_list():
    """从 akshare 获取 A 股 + ETF 列表并写入数据库"""
    import akshare as ak
    try:
        df = ak.stock_info_a_code_name()
        rows = []
        for _, row in df.iterrows():
            code = str(row['code'])
            if not code.startswith(('0', '3', '6', '15', '16', '51')): continue
            name = str(row['name'])
            if code.startswith(('15', '16')): market = '0'
            elif code.startswith('51'): market = '1'
            elif code.startswith(('6',)): market = '1'
            else: market = '0'
            rows.append((code, market, name))
        stocks_save(rows)
        return len(rows)
    except Exception as e:
        print(f"[market_db] 股票列表获取失败: {e}")
        return 0


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
        print(f"[market_db] 所有股票数据已是最新，跳过")
        return

    print(f"[market_db] {len(need_update)}/{len(stocks)} 只需更新")
    total = len(need_update)
    done = 0

    with ThreadPoolExecutor(max_workers=4) as pool:
        futs = {pool.submit(_sync_one_stock, s[0], s[1], ('daily',)): s for s in need_update}
        for fut in as_completed(futs):
            try:
                fut.result()
            except Exception:
                pass
            done += 1
            if done % 200 == 0 or done == total:
                print(f"[market_db] 增量进度 {done}/{total}")

    # 周K/月K也增量一下
    with ThreadPoolExecutor(max_workers=4) as pool:
        futs = {pool.submit(_sync_one_stock, s[0], s[1], ('weekly', 'monthly')): s for s in need_update}
        for fut in as_completed(futs):
            try:
                fut.result()
            except Exception:
                pass
            done += 1
            if done % 200 == 0 or done == total:
                print(f"[market_db] 周月K进度 {done - total}/{total}")

    elapsed = time.time() - t0
    print(f"[market_db] 增量更新完成，耗时 {elapsed:.0f}s（{len(need_update)} 只）")


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
    all_stocks = stocks_all()
    if not all_stocks:
        _fetch_stock_list()
        all_stocks = stocks_all()
    stocks = [s for s in all_stocks if s[0].startswith(prefix)]
    if not stocks:
        _sync_state.update({'running': False, 'done': 0, 'total': 0, 'errors': 0})
        return

    _sync_state.update({'running': True, 'label': seg['label'], 'total': len(stocks), 'done': 0, 'errors': 0})

    with ThreadPoolExecutor(max_workers=4) as pool:
        futs = {pool.submit(_sync_one_stock, s[0], s[1], ('daily',)): s for s in stocks}
        for fut in as_completed(futs):
            try:
                fut.result()
            except Exception:
                _sync_state['errors'] += 1
            _sync_state['done'] += 1

    with ThreadPoolExecutor(max_workers=4) as pool:
        futs = {pool.submit(_sync_one_stock, s[0], s[1], ('weekly', 'monthly')): s for s in stocks}
        for fut in as_completed(futs):
            try:
                fut.result()
            except Exception:
                _sync_state['errors'] += 1
            _sync_state['done'] += len(stocks)

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
