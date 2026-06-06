"""全市场数据同步
启动时：
  1. 刷新 stock_list.db：按市场拉取在市的股票列表（有日期判断，同日不重复拉）
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


def _today_str():
    return datetime.date.today().strftime('%Y-%m-%d')


# =========== 步骤 1：刷新股票列表 ===========

def _fetch_active_stocks():
    """从 akshare 获取全市场在市的 A 股 + ETF，返回 [(code, market, name), ...]"""
    import akshare as ak

    all_rows = []

    # —— A 股 ——
    print("[sync] 获取 A 股列表...")
    try:
        df = ak.stock_zh_a_spot_em()
    except Exception:
        try:
            df = ak.stock_info_a_code_name()
        except Exception as e:
            print(f"[sync] A 股列表获取失败: {e}")
            return None

    if df is None or df.empty:
        print("[sync] A 股列表为空")
        return None

    for _, row in df.iterrows():
        code = str(row.get('代码', row.get('code', ''))).zfill(6)
        name = str(row.get('名称', row.get('name', '')))
        if not code.isdigit() or len(code) != 6:
            continue
        if code.startswith(('15', '16')):
            market = '0'
        elif code.startswith('51'):
            market = '1'
        elif code.startswith(('6',)):
            market = '1'
        else:
            market = '0'
        all_rows.append((code, market, name))
    print(f"[sync] A 股: {len(all_rows)} 只")

    # —— ETF ——
    print("[sync] 获取 ETF 列表...")
    try:
        df_etf = ak.fund_etf_spot_em()
    except Exception as e:
        print(f"[sync] ETF 列表获取失败: {e}")
        return all_rows  # ETF 失败不影响 A 股

    etf_count = 0
    for _, row in df_etf.iterrows():
        code = str(row.get('代码', row.get('code', ''))).zfill(6)
        name = str(row.get('名称', row.get('name', '')))
        if not code.isdigit() or len(code) != 6:
            continue
        if code.startswith(('15', '16')):
            market = '0'
        elif code.startswith('51'):
            market = '1'
        else:
            continue
        all_rows.append((code, market, name))
        etf_count += 1
    print(f"[sync] ETF: {etf_count} 只，总计 {len(all_rows)} 只")
    return all_rows


def _refresh_stock_list():
    """刷新 stock_list.db：只更新已存在的市场类型，不新增"""
    today = _today_str()
    markets = list_markets()

    if not markets:
        print("[sync] stock_list.db 为空，跳过列表刷新（需手动初始化市场类型）")
        return

    # 检查是否所有 market 今天已同步
    all_synced = all(list_sync_date_get(m) == today for m in markets)
    if all_synced:
        print("[sync] 股票列表已是最新（今日已更新），跳过")
        return

    print("[sync] 获取在市的股票列表...")
    all_rows = _fetch_active_stocks()
    if all_rows is None:
        print("[sync] 获取失败，保留现有列表")
        return

    # 按 market 分组
    by_market = {}
    for code, market, name in all_rows:
        by_market.setdefault(market, []).append((code, name))

    # 只更新 stock_list.db 中已存在的 market
    for m in markets:
        rows = by_market.get(m, [])
        list_replace_market(m, rows)
        list_sync_date_set(m, today)
        print(f"[sync] 市场 {m} 股票列表已更新: {len(rows)} 只")


# =========== 步骤 2：同步 K 线 ===========

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


def _sync_one_stock(code, market, name, periods=('daily', 'weekly', 'monthly')):
    """同步单只股票所有周期的 K 线"""
    today = _today_str()
    info = detail_info_get(code, market)
    max_date = info['latest_kline_date'] if info else None

    if max_date and max_date >= today:
        return  # 今天已是最新，跳过

    all_rows = []
    for period in periods:
        if max_date and max_date != '':
            # 增量：从最后一天 + 1 天开始
            last = datetime.date.fromisoformat(max_date)
            start = (last + datetime.timedelta(days=1)).strftime('%Y%m%d')
        else:
            # 全量
            start = '19900101'
        end = today.replace('-', '')
        rows = _fetch_kline(code, market, period, start, end)
        for r in rows:
            all_rows.append(r)

    if all_rows:
        detail_klines_insert(all_rows)
        # 更新 latest_kline_date
        latest = max(r[3] for r in all_rows)  # date 是第 4 列
    else:
        latest = max_date or ''

    detail_info_upsert(code, market, name or code, latest)


def _sync_klines():
    """遍历 stock_list.db，增量同步 K 线到 stock_detail_list.db"""
    stocks = list_stocks_all()
    if not stocks:
        print("[sync] 股票列表为空，跳过 K 线同步")
        return

    total = len(stocks)
    print(f"[sync] 开始同步 K 线 ({total} 只，4 线程增量)...")

    t0 = time.time()
    done = 0

    with ThreadPoolExecutor(max_workers=4) as pool:
        futs = {pool.submit(_sync_one_stock, s[0], s[1], s[2]): s for s in stocks}
        for fut in as_completed(futs):
            try:
                fut.result()
            except Exception:
                pass
            done += 1
            if done % 500 == 0 or done == total:
                pct = done / total * 100
                el = time.time() - t0
                eta = el / done * (total - done) if done > 0 else 0
                bar = '█' * int(30 * done / total) + '░' * (30 - int(30 * done / total))
                print(f"\r[sync] K线 [{bar}] {pct:5.1f}% {done}/{total}  耗时 {el:.0f}s 预计剩余 {eta:.0f}s", end='', flush=True)
    print()
    print(f"[sync] K 线同步完成，耗时 {time.time()-t0:.0f}s")


# =========== 步骤 3：清理退市 ===========

def _cleanup_delisted():
    """detail DB 中在 list DB 里不存在的股票 → 退市，删除"""
    active = set((s[0], s[1]) for s in list_stocks_all())
    if not active:
        print("[sync] 股票列表为空，跳过退市清理")
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

def init_market(market):
    """初始化一个新市场：拉取股票列表 + 全量同步 K 线"""
    if market in list_markets():
        print(f"[sync] 市场 {market} 已存在，跳过初始化")
        return {'success': False, 'error': '市场已存在'}

    print(f"[sync] 初始化新市场: {market}")
    all_rows = _fetch_active_stocks()
    if all_rows is None:
        return {'success': False, 'error': '无法获取股票列表'}

    # 过滤出该市场
    rows = [(c, n) for c, m, n in all_rows if m == market]
    if not rows:
        return {'success': False, 'error': f'市场 {market} 无股票'}

    today = _today_str()
    list_replace_market(market, rows)
    list_sync_date_set(market, today)
    print(f"[sync] 市场 {market} 股票列表已写入: {len(rows)} 只")

    # 立即增量同步 K 线
    stocks = [(c, market, n) for c, n in rows]
    print(f"[sync] 开始全量同步 K 线 ({len(stocks)} 只，4 线程)...")

    import time
    t0 = time.time()
    done = 0
    with ThreadPoolExecutor(max_workers=4) as pool:
        futs = {pool.submit(_sync_one_stock, s[0], s[1], s[2]): s for s in stocks}
        for fut in as_completed(futs):
            try: fut.result()
            except Exception: pass
            done += 1
            if done % 500 == 0 or done == len(stocks):
                pct = done / len(stocks) * 100
                el = time.time() - t0
                eta = el / done * (len(stocks) - done) if done > 0 else 0
                bar = '█' * int(30 * done / len(stocks)) + '░' * (30 - int(30 * done / len(stocks)))
                print(f"\r[sync] K线 [{bar}] {pct:5.1f}% {done}/{len(stocks)}  耗时 {el:.0f}s 预计剩余 {eta:.0f}s", end='', flush=True)
    print()

    # 清理退市
    _cleanup_delisted()
    print(f"[sync] 市场 {market} 初始化完成，耗时 {time.time()-t0:.0f}s")
    return {'success': True, 'stocks': len(stocks)}


# =========== 启动入口 ===========

def _startup_worker():
    """后台线程执行全量启动同步"""
    print("[sync] ===== 启动数据同步 =====")

    try:
        _refresh_stock_list()
    except RuntimeError as e:
        print(f"[sync] 致命错误: {e}")
        return

    _sync_klines()
    _cleanup_delisted()
    print("[sync] ===== 同步完成 =====\n")


def init_stock_list_only():
    """首次启动：仅初始化股票列表（不拉 K 线）"""
    print("[sync] 初始化股票列表...")
    _refresh_stock_list()
    print("[sync] 股票列表就绪")


def start_startup_sync():
    """启动后台同步线程"""
    t = threading.Thread(target=_startup_worker, daemon=True, name='market-sync')
    t.start()
