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
    detail_info_all, detail_info_get, detail_info_upsert, detail_info_date_map,
    detail_klines_insert, detail_remove_stock, detail_sync_atomic, detail_clear_market,
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
    'hk_main': {'label': '港股',   'fs': 'm:116+t:3',       'api': 'eastmoney'},
    'us_main': {'label': '美股',   'fs': 'm:105,m:106,m:107',       'api': 'eastmoney'},
}


def _today_str():
    return datetime.date.today().strftime('%Y-%m-%d')


def _code_to_segment(code):
    """代码 → segment key（仅 A 股/ETF 按前缀匹配，港股/美股留空由调用方指定）"""
    for key, seg in SEGMENTS.items():
        if 'prefix' not in seg:
            continue
        for p in seg['prefix']:
            if code.startswith(p):
                return key
    return None


# =========== 步骤 1：刷新股票列表 ===========

def _fetch_us_stocks():
    """从 NASDAQ 官方 screener API 拉取全量美股列表"""
    import requests
    import time as _time

    url = 'https://api.nasdaq.com/api/screener/stocks'
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'en-US,en;q=0.9',
    }
    params = {'tableonly': 'true', 'download': 'true'}

    print(f"[sync] 拉取 美股 列表 (NASDAQ API)...")
    for attempt in range(3):
        try:
            r = requests.get(url, params=params, headers=headers, timeout=30)
            if r.status_code != 200:
                if attempt < 2:
                    _time.sleep(3 * (attempt + 1))
                    continue
                print(f"[sync] 美股 NASDAQ API HTTP {r.status_code}")
                return []
            jd = r.json()
            rows = (jd.get('data') or {}).get('rows') or []
            if not rows:
                print(f"[sync] 美股 NASDAQ API 返回空")
                return []
            result = []
            for row in rows:
                code = str(row.get('symbol', '')).strip()
                name = str(row.get('name', '')).strip()
                price_str = str(row.get('lastsale', '')).replace('$', '').strip()
                if not code or not name:
                    continue
                # 排除优先股/权证等非普通股（含 ^ / 等特殊符号）
                if any(c in code for c in ('^', '/', '.')):
                    continue
                try:
                    price = float(price_str) if price_str else 0
                except ValueError:
                    price = 0
                if price <= 0:
                    continue
                result.append((code, name))
            print(f"[sync] 美股: {len(result)} 只")
            return result
        except Exception as e:
            if attempt < 2:
                _time.sleep(3 * (attempt + 1))
            else:
                print(f"[sync] 美股 NASDAQ API 失败: {e}")
    return []


def _fetch_stocks_by_segment(seg_key):
    """只拉取指定分段的市场股票列表"""
    import requests
    import time as _time

    seg = SEGMENTS[seg_key]
    label = seg['label']

    # 美股用 NASDAQ 官方 API（东方财富覆盖不全）
    if seg_key == 'us_main':
        return _fetch_us_stocks()

    url = 'https://push2delay.eastmoney.com/api/qt/clist/get'
    headers = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://data.eastmoney.com/'}

    # 根据分段选 fs 过滤器和代码处理方式
    is_overseas = seg_key == 'hk_main'
    if seg_key in ('sh_main', 'sz_main', 'gem', 'star', 'bj', 'xsb'):
        fs_filter = 'm:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23'
    elif seg_key in ('sz_etf', 'sh_etf'):
        fs_filter = 'b:MK0021,b:MK0022,b:MK0023,b:MK0024'
    elif is_overseas:
        fs_filter = seg['fs']
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
        total_count = data.get('total', 0)
        if is_overseas and total_count:
            print(f"\r[sync] {label} 第{page}页: +{len(items)} 只 (API总量 {total_count})", end='', flush=True)
        for row in items:
            code = str(row.get('f12', ''))
            name = str(row.get('f14', ''))
            price = row.get('f2')
            # 退市/长期停牌：价格为 '-' 或 None，排除
            if price is None or price == '-' or str(price).strip() == '':
                continue
            if is_overseas:
                # 港股: 代码如 "00700"，去掉前导零后补4位 → Yahoo Finance 格式
                code = code.strip().lstrip('0') or code.strip()
                code = code.zfill(4)
                if not code.isdigit():
                    continue
            else:
                code = code.zfill(6)
                if len(code) != 6 or not code.isdigit():
                    continue
                seg_chk = _code_to_segment(code)
                if seg_chk != seg_key:
                    continue
                if seg_key in ('sz_etf', 'sh_etf'):
                    if not any(code.startswith(p) for p in SEGMENTS[seg_key]['prefix']):
                        continue
            all_rows.append((code, name))
        page += 1
        _time.sleep(0.1)
    print(f"[sync] {label}: {len(all_rows)} 只")
    return all_rows


def _fetch_active_stocks(markets):
    """拉取指定市场分段的股票列表"""
    all_rows = []
    for seg_key in markets:
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

    print(f"[sync] 获取在市的股票列表 (已存在 {len(markets)} 个分段: {', '.join(markets)})...")
    all_rows = _fetch_active_stocks(markets)
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

def _parse_date(date_str):
    """将 'YYYYMMDD' 字符串转为 date 对象"""
    import datetime as _dt
    return _dt.datetime.strptime(date_str, '%Y%m%d').date()


def _fetch_kline(code, seg_key, period, start_date, end_date):
    """获取 K 线：A股用腾讯 API，港股/美股用 Yahoo Finance"""
    import requests as _rq

    if seg_key in ('hk_main', 'us_main'):
        return _fetch_kline_yahoo(code, seg_key, period, start_date, end_date)

    c = str(code)
    pfx = 'sh' if c.startswith(('6', '9')) else 'sz'
    tp_map = {'daily': ('day', 800), 'weekly': ('week', 200), 'monthly': ('month', 40)}

    # 增量场景：计算实际需要的条数，减少不必要的网络传输
    if start_date and start_date != '19900101' and end_date:
        try:
            start_dt = _parse_date(start_date)
            end_dt = _parse_date(end_date)
            delta_days = (end_dt - start_dt).days
            if period == 'daily':
                need = min(delta_days + 10, 800)  # 按间隔天数 + 缓冲
            elif period == 'weekly':
                need = min(max(10, delta_days // 7 + 3), 200)
            elif period == 'monthly':
                need = min(max(3, delta_days // 30 + 2), 40)
            tp, _ = tp_map.get(period, ('day', 800))
        except Exception:
            tp, need = tp_map.get(period, ('day', 800))
    else:
        tp, need = tp_map.get(period, ('day', 800))

    for attempt in range(3):
        try:
            r = _rq.get(
                "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get",
                params={'param': f"{pfx}{c},{tp},,,{need},qfq"},
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
                raw = sd.get('qfqday') or sd.get('day') or []
            elif tp == 'week':
                raw = sd.get('qfqweek') or sd.get('week') or []
            else:
                raw = sd.get('qfqmonth') or sd.get('month') or []
            if not raw:
                print(f"\r[sync]  ! {code} {period}: API 返回空 (HTTP {r.status_code})", flush=True)
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
                # row[6] 在除权除息日为 dict（分红信息），此时成交额填 0
                if len(row) >= 7 and not isinstance(row[6], dict):
                    amount = float(row[6])
                else:
                    amount = 0
                rows.append((
                    code, seg_key, period,
                    date_str,
                    float(row[1]), float(row[3]), float(row[4]),
                    float(row[2]), float(row[5]),
                    amount,
                ))
            return rows
        except Exception as e:
            if attempt < 2:
                time.sleep(2 * (attempt + 1))
            else:
                print(f"\r[sync]  ! {code} {period}: 请求失败 ({type(e).__name__}: {e})", flush=True)
    return []


# ---- Yahoo Finance 限流 ----

_yahoo_rate_lock = threading.Lock()
_yahoo_last_req = 0.0
_YAHOO_MIN_INTERVAL = 0.15  # 全局最低请求间隔（秒），约 6~7 req/s

# 统计同步失败数（线程安全）
_sync_fail_count = 0
_sync_fail_lock = threading.Lock()

# 正在同步的市场集合（按市场粒度互斥，不同市场可并行）
_syncing_markets = set()  # 元素: seg_key 如 'us_main'，或 '*' 表示全市场
_syncing_markets_lock = threading.Lock()


def _fetch_kline_yahoo(code, seg_key, period, start_date, end_date):
    """Yahoo Finance K 线（港股/美股），与 app.py 对齐：
    - 用 query1.finance.yahoo.com（无需 crumb/cookie）
    - 临时移除 no_proxy，允许走系统代理访问被墙的 Yahoo"""
    global _yahoo_last_req, _sync_fail_count
    import requests as _rq
    import datetime as _dt
    import os as _os

    # 构建 Yahoo Finance symbol
    if seg_key == 'hk_main':
        symbol = str(int(code)).zfill(4) + '.HK'
    else:
        symbol = code

    yh_intv = {'daily': '1d', 'weekly': '1wk', 'monthly': '1mo'}.get(period, '1d')

    # DEBUG: 仅首次打印
    if not hasattr(_fetch_kline_yahoo, '_debug_done'):
        _fetch_kline_yahoo._debug_done = True
        print(f"[sync] DEBUG _fetch_kline_yahoo 首次: symbol={symbol} period={period} start={start_date} end={end_date}", flush=True)

    for attempt in range(4):
        # 限流：全局最低间隔，避免被 Yahoo 封 IP
        with _yahoo_rate_lock:
            elapsed = time.time() - _yahoo_last_req
            if elapsed < _YAHOO_MIN_INTERVAL:
                time.sleep(_YAHOO_MIN_INTERVAL - elapsed)
            _yahoo_last_req = time.time()

        # 临时移除 no_proxy，让 requests 走系统代理（中国环境访问 Yahoo 需要）
        _old_no = _os.environ.pop('no_proxy', None)
        _old_NO = _os.environ.pop('NO_PROXY', None)
        try:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=max&interval={yh_intv}"
            r = _rq.get(url, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            }, timeout=15)

            if r.status_code == 404:
                return []  # 股票代码不存在，不重试

            if r.status_code != 200:
                if attempt < 2:
                    time.sleep(2 * (attempt + 1))
                    continue
                return []

            result = (r.json().get('chart', {}).get('result') or [None])[0]
            if not result:
                return []
            timestamps = result.get('timestamp') or []
            quotes = (result.get('indicators', {}).get('quote') or [None])[0]
            if not quotes or not timestamps:
                return []
            rows = []
            for i, ts in enumerate(timestamps):
                o = quotes['open'][i]
                if o is None:
                    continue
                dt_val = _dt.datetime.fromtimestamp(ts, tz=_dt.timezone.utc)
                date_str = dt_val.strftime('%Y%m%d')
                if start_date and date_str < start_date:
                    continue
                if end_date and date_str > end_date:
                    continue
                rows.append((
                    code, seg_key, period,
                    date_str,
                    round(float(o), 3),
                    round(float(quotes['high'][i] or 0), 3),
                    round(float(quotes['low'][i] or 0), 3),
                    round(float(quotes['close'][i] or 0), 3),
                    int(quotes['volume'][i] or 0),
                    round(float(quotes['close'][i] or 0) * int(quotes['volume'][i] or 0), 2),
                ))
            return rows
        except Exception:
            if attempt < 3:
                time.sleep(1.5 * (attempt + 1))
            else:
                with _sync_fail_lock:
                    _sync_fail_count += 1
        finally:
            if _old_no is not None:
                _os.environ['no_proxy'] = _old_no
            if _old_NO is not None:
                _os.environ['NO_PROXY'] = _old_NO
    return []


def _latest_possible_trading_day():
    """估算最近的交易日：周末回退到周五，避免非交易日触发无意义的增量拉取
    返回 'YYYYMMDD' 格式，与 stock_info.latest_kline_date 保持一致"""
    today = datetime.date.today()
    wd = today.weekday()  # 0=Mon ... 6=Sun
    if wd == 5:      # 周六 → 周五
        return (today - datetime.timedelta(days=1)).strftime('%Y%m%d')
    elif wd == 6:    # 周日 → 周五
        return (today - datetime.timedelta(days=2)).strftime('%Y%m%d')
    return today.strftime('%Y%m%d')


def _sync_one_stock(code, market, name, max_date_map, latest_trading, periods=('daily', 'weekly', 'monthly'), force_today=False):
    """同步单只股票所有周期的 K 线（max_date_map 和 latest_trading 由调用方预加载，避免逐只查 DB）"""
    if _sync_status.get('cancel'):
        return

    max_date = max_date_map.get((code, market), None)

    if max_date and max_date >= latest_trading and not force_today:
        return

    # DEBUG: 仅首只打印，确认执行到了 fetch 逻辑
    if not hasattr(_sync_one_stock, '_debug_done'):
        _sync_one_stock._debug_done = True
        print(f"\n[sync] DEBUG _sync_one_stock 首只: code={code} market={market} name={name} max_date={max_date} latest_trading={latest_trading} periods={periods}", flush=True)

    # 增量：只差几天时，周线/月线无需重拉（新周期尚未生成）
    if max_date:
        try:
            gap = (_parse_date(latest_trading) - _parse_date(max_date)).days
        except Exception:
            gap = None
        if gap is not None and gap <= 7:
            periods = ('daily',)
        elif gap is not None and gap <= 31:
            periods = ('daily', 'weekly')

    try:
        all_rows = []
        for period in periods:
            if max_date and max_date != '':
                last = _parse_date(max_date)
                if force_today and max_date == latest_trading:
                    start = max_date  # 强制重拉当日完整数据
                else:
                    start = (last + datetime.timedelta(days=1)).strftime('%Y%m%d')
            else:
                start = '19900101'
            end = latest_trading
            rows = _fetch_kline(code, market, period, start, end)
            for r in rows:
                all_rows.append(r)

        if all_rows:
            latest = max(r[3] for r in all_rows)
            detail_sync_atomic(code, market, name, all_rows, latest)
            print(f"\r[sync]  ✔ {code} {name} → {latest} (+{len(all_rows)}条)", flush=True)
        else:
            if max_date:
                detail_info_upsert(code, market, name or code, max_date)
                print(f"\r[sync]  ~ {code} {name} 无新数据 (已有 {max_date})", flush=True)
            else:
                print(f"\r[sync]  ✘ {code} {name} API 返回空 (periods={periods}, start={start if max_date else '19900101'})", flush=True)
    except Exception as _e:
        if not hasattr(_sync_one_stock, '_err_printed'):
            _sync_one_stock._err_printed = True
            print(f"\n[sync] !!! _sync_one_stock 异常 [{code}]: {type(_e).__name__}: {_e}", flush=True)
        raise


def _sync_klines(markets=None, force_today=False):
    """遍历 stock_list.db，增量同步 K 线。markets 可选：只同步指定市场列表。
    force_today=True 时，即使 latest_kline_date == 当天也会重新拉取（收市后定时同步使用）。"""
    global _sync_status
    stocks = list_stocks_all()
    if markets:
        stocks = [s for s in stocks if s[1] in markets]
    if not stocks:
        print("[sync] 股票列表为空，跳过 K 线同步")
        return

    global _sync_fail_count
    _sync_fail_count = 0

    # 预加载，避免每条股票都开一次 DB 连接
    max_date_map = detail_info_date_map()
    latest_trading = _latest_possible_trading_day()

    # 过滤：只同步需要更新的股票
    # force_today 时包含当日已同步过的股票，确保收市后拿到完整日K
    if force_today:
        to_sync = [s for s in stocks if max_date_map.get((s[0], s[1]), '') <= latest_trading]
    else:
        to_sync = [s for s in stocks if max_date_map.get((s[0], s[1]), '') < latest_trading]
    skipped = len(stocks) - len(to_sync)
    total = len(to_sync)
    _sync_status['total'] = total
    _sync_status['done'] = 0
    _sync_status['phase'] = 'kline'

    if total == 0:
        print(f"[sync] K 线已是最新 ({skipped} 只)，无需更新")
        return

    print(f"[sync] 开始同步 K 线 (已是最新: {skipped} 只，需要更新: {total} 只，4 线程增量)...")

    t0 = time.time()

    with ThreadPoolExecutor(max_workers=4) as pool:
        futs = {pool.submit(_sync_one_stock, s[0], s[1], s[2], max_date_map, latest_trading, ('daily', 'weekly', 'monthly'), force_today): s for s in to_sync}
        for fut in as_completed(futs):
            if _sync_status.get('cancel'):
                break
            try:
                fut.result()
            except Exception:
                pass
            _sync_status['done'] += 1
            # 前 4 只每完成一只都打，之后每 10 只一报
            if _sync_status['done'] <= 4 or _sync_status['done'] % 10 == 0 or _sync_status['done'] == total:
                pct = _sync_status['done'] / total * 100
                el = time.time() - t0
                eta = el / _sync_status['done'] * (total - _sync_status['done']) if _sync_status['done'] > 0 else 0
                bar = '█' * int(30 * _sync_status['done'] / total) + '░' * (30 - int(30 * _sync_status['done'] / total))
                print(f"\r[sync] K线 [{bar}] {pct:5.1f}% {_sync_status['done']}/{total}  耗时 {el:.0f}s 预计剩余 {eta:.0f}s", end='', flush=True)
    print()
    el = time.time() - t0
    if _sync_fail_count > 0:
        print(f"[sync] K 线同步完成 (失败 {_sync_fail_count} 只)，耗时 {el:.0f}s")
    else:
        print(f"[sync] K 线同步完成，耗时 {el:.0f}s")


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

_sync_status = {'running': False, 'label': '', 'total': 0, 'done': 0, 'phase': '', 'cancel': False, 'seg_key': None}

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

    # 按市场粒度检查冲突：不同市场可并行
    with _syncing_markets_lock:
        if '*' in _syncing_markets or seg_key in _syncing_markets:
            return {'success': False, 'error': '该市场正在同步中'}
        _syncing_markets.add(seg_key)

    _sync_status['running'] = True
    _sync_status['label'] = SEGMENTS[seg_key]['label']
    _sync_status['seg_key'] = seg_key
    threading.Thread(target=_run_init, args=(seg_key,), daemon=True).start()
    return {'success': True, 'message': '初始化已启动'}

def _run_init(seg_key):
    global _sync_status
    try:
        label = SEGMENTS[seg_key]['label']
        _sync_status['phase'] = 'list'
        _sync_status['cancel'] = False
        print(f"[sync] 初始化: {label}")

        rows = _fetch_stocks_by_segment(seg_key)
        if not rows:
            _sync_status['running'] = False
            _sync_status['phase'] = 'error'
            _sync_status['error'] = f'{label} 暂不支持（API 无此市场数据）'
            _sync_status['total'] = 0
            _sync_status['done'] = 0
            return

        # 检查点 1：列表拉完但尚未写入 DB
        if _sync_status.get('cancel'):
            _sync_status['running'] = False
            _sync_status['phase'] = 'cancelled'
            _sync_status['cancel'] = False
            print(f"[sync] {label} 加载已被终止")
            return

        list_replace_market(seg_key, rows)
        print(f"[sync] {label} 股票列表已写入: {len(rows)} 只")

        # 检查点 1.5：列表已写入 DB，检测到取消则回滚
        if _sync_status.get('cancel'):
            list_replace_market(seg_key, [])
            list_sync_date_set(seg_key, None)
            _sync_status['running'] = False
            _sync_status['phase'] = 'cancelled'
            _sync_status['cancel'] = False
            print(f"[sync] {label} 加载已被终止（列表已回滚）")
            return

        stocks = [(c, seg_key, n) for c, n in rows]
        _sync_status['total'] = len(stocks)
        _sync_status['done'] = 0
        _sync_status['phase'] = 'kline'
        global _sync_fail_count
        _sync_fail_count = 0
        print(f"[sync] 开始全量同步 K 线 ({len(stocks)} 只，4 线程)...")

        t0 = time.time()
        max_date_map = {}
        latest_trading = _latest_possible_trading_day()
        cancelled = False
        with ThreadPoolExecutor(max_workers=4) as pool:
            futs = {pool.submit(_sync_one_stock, s[0], s[1], s[2], max_date_map, latest_trading): s for s in stocks}
            for fut in as_completed(futs):
                if _sync_status.get('cancel'):
                    cancelled = True
                    break
                try:
                    fut.result()
                except Exception:
                    pass
                _sync_status['done'] += 1
                step = 50
                if _sync_status['done'] % step == 0 or _sync_status['done'] == len(stocks):
                    pct = _sync_status['done'] / len(stocks) * 100
                    el = time.time() - t0
                    eta = el / _sync_status['done'] * (len(stocks) - _sync_status['done']) if _sync_status['done'] > 0 else 0
                    bar = '█' * int(30 * _sync_status['done'] / len(stocks)) + '░' * (30 - int(30 * _sync_status['done'] / len(stocks)))
                    print(f"\r[sync] K线 [{bar}] {pct:5.1f}% {_sync_status['done']}/{len(stocks)}  耗时 {el:.0f}s 预计剩余 {eta:.0f}s", end='', flush=True)
        print()

        # 检查点 2：K 线同步中被取消，回滚所有数据
        if cancelled:
            detail_clear_market(seg_key)
            list_replace_market(seg_key, [])
            list_sync_date_set(seg_key, None)
            _sync_status['running'] = False
            _sync_status['phase'] = 'cancelled'
            _sync_status['cancel'] = False
            print(f"[sync] {label} K线同步已被终止，数据已回滚")
            return

        _cleanup_delisted()
        list_sync_date_set(seg_key, _today_str())
        el = time.time() - t0
        if _sync_fail_count > 0:
            print(f"[sync] {label} 初始化完成 (K线失败 {_sync_fail_count} 只)，耗时 {el:.0f}s")
        else:
            print(f"[sync] {label} 初始化完成，耗时 {el:.0f}s")
    finally:
        if _sync_status['phase'] not in ('cancelled', 'error'):
            _sync_status['running'] = False
            _sync_status['phase'] = 'done'
        with _syncing_markets_lock:
            _syncing_markets.discard(seg_key)

def get_init_status():
    return dict(_sync_status)


def cancel_init():
    """终止当前运行中的同步任务"""
    global _sync_status
    if not _sync_status['running']:
        return {'success': False, 'error': '没有运行中的同步任务'}
    if _sync_status.get('cancel'):
        return {'success': False, 'error': '正在终止中，请稍候'}
    _sync_status['cancel'] = True
    label = _sync_status.get('label', '')
    return {'success': True, 'message': '正在终止' + (label + ' ' if label else '') + '数据加载...'}


def get_segments_info():
    """返回各分段状态，含当前加载状态"""
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
    return {
        'segments': result,
        'init_running': _sync_status.get('running', False),
        'init_seg_key': _sync_status.get('seg_key'),
        'init_phase': _sync_status.get('phase'),
    }


# =========== 清库 ===========

def clear_market(seg_key):
    """清除指定市场的所有数据（列表 + K线 + 元信息 + 同步记录）"""
    if seg_key not in SEGMENTS:
        return {'success': False, 'error': '无效的市场分段'}
    if seg_key not in list_markets():
        return {'success': False, 'error': '该市场无数据可清除'}

    # 只阻断同市场的并发清库（不同市场操作不同行，互不干扰）
    with _syncing_markets_lock:
        if '*' in _syncing_markets or seg_key in _syncing_markets:
            return {'success': False, 'error': '正在同步中，请先终止加载后再清库'}

    label = SEGMENTS[seg_key]['label']
    print(f"[sync] 清除 {label} 数据...")

    # 1. 清除 detail 库中的 K 线和元信息
    detail_clear_market(seg_key)

    # 2. 清除 list 库中的股票列表和同步记录
    list_replace_market(seg_key, [])
    list_sync_date_set(seg_key, None)  # 清掉同步时间戳

    print(f"[sync] {label} 数据已清除")
    return {'success': True, 'message': f'{label} 数据已清除'}


# =========== 启动入口 ===========

def _startup_worker():
    """后台线程：只更新已有市场，不新增"""
    global _sync_status
    with _syncing_markets_lock:
        _syncing_markets.add('*')  # 全市场标记，与所有市场冲突
    _sync_status['running'] = True
    _sync_status['label'] = '增量同步'
    _sync_status['cancel'] = False
    _sync_status['seg_key'] = None  # startup 全市场同步，清库全部拦截
    print("[sync] ===== 启动增量同步 =====")
    _sync_status['phase'] = 'list'
    _refresh_stock_list()
    if _sync_status.get('cancel'):
        _sync_status['running'] = False
        _sync_status['phase'] = 'cancelled'
        _sync_status['cancel'] = False
        with _syncing_markets_lock:
            _syncing_markets.discard('*')
        print("[sync] ===== 同步被终止 =====\n")
        return
    _sync_klines()
    if _sync_status.get('cancel'):
        _sync_status['running'] = False
        _sync_status['phase'] = 'cancelled'
        _sync_status['cancel'] = False
        with _syncing_markets_lock:
            _syncing_markets.discard('*')
        print("[sync] ===== 同步被终止 =====\n")
        return
    _sync_status['phase'] = 'cleanup'
    _cleanup_delisted()
    # 全部完成后才更新时间戳
    today = _today_str()
    for m in list_markets():
        list_sync_date_set(m, today)
    _sync_status['running'] = False
    _sync_status['phase'] = 'done'
    with _syncing_markets_lock:
        _syncing_markets.discard('*')
    print("[sync] ===== 同步完成 =====\n")


# =========== 收市后定时增量同步 ===========

import datetime as _dt_module

# 收市后增量同步时间表 (UTC+8 北京时间)
# (hour, minute): (label, [markets])
_CLOSE_SCHEDULE = [
    (14, 30, '港股', ['hk_main']),
    (15, 30, 'A股', ['sh_main', 'sz_main', 'gem', 'star', 'sz_etf', 'sh_etf', 'bj']),
    (4, 30, '美股', ['us_main']),
]

_last_scheduled_sync = {}  # {group_label: date_str}


def _schedule_loop():
    """后台线程：每 60 秒检查，收市 30 分钟后触发指定市场增量同步"""
    global _sync_status
    print("[sync] 定时同步调度已启动")
    while True:
        try:
            now = _dt_module.datetime.now()
            today_str = now.strftime('%Y-%m-%d')
            wd = now.weekday()

            # 周末跳过
            if wd >= 5:
                time.sleep(60)
                continue

            for h, m, label, candidate_markets in _CLOSE_SCHEDULE:
                if now.hour == h and now.minute == m:
                    if _last_scheduled_sync.get(label) == today_str:
                        continue  # 今天已同步过

                    # 只同步 stock_list.db 里已有的市场，没加载的不触发
                    existing = [mk for mk in candidate_markets if mk in list_markets()]
                    if not existing:
                        continue

                    # 按市场粒度检查冲突：不同市场可并行
                    with _syncing_markets_lock:
                        target_set = set(existing)
                        overlap = target_set & _syncing_markets
                        if '*' in _syncing_markets or overlap:
                            continue
                        _syncing_markets.update(existing)

                    print(f"\n[sync] ===== 定时同步: {label} =====")
                    _last_scheduled_sync[label] = today_str
                    _sync_status['running'] = True
                    _sync_status['cancel'] = False
                    _sync_status['label'] = f'{label}定时'
                    _sync_status['phase'] = 'kline'

                    try:
                        _sync_klines(markets=existing, force_today=True)
                        _cleanup_delisted()
                        for m in existing:
                            list_sync_date_set(m, today_str)
                    finally:
                        _sync_status['running'] = False
                        _sync_status['phase'] = 'done'
                        with _syncing_markets_lock:
                            _syncing_markets.difference_update(existing)
                    print(f"[sync] ===== 定时同步: {label} 完成 =====\n")

            time.sleep(60)
        except Exception as e:
            print(f"[sync] 定时调度异常: {e}")
            time.sleep(60)


def start_startup_sync():
    t = threading.Thread(target=_startup_worker, daemon=True, name='market-sync')
    t.start()
    # 同时启动收市定时同步
    threading.Thread(target=_schedule_loop, daemon=True, name='market-schedule').start()
