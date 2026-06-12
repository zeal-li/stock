"""全市场数据同步
加载（初始化）：
  1. 拉取股票列表 → 写入 stock_list.db
  2. 全量同步 K 线 → 写入 stock_detail_list.db
  3. 清理退市
  4. 更新 stocks.sync_ts

更新（增量）：
  1. 检查 stocks.sync_ts，判断是否需要更新
  2. 拉取最新股票列表 → 替换 stock_list.db
  3. 增量同步 K 线
  4. 更新 stocks.sync_ts
  5. 清理退市
"""
import datetime
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from .db import (
    list_markets, list_replace_market, list_sync_ts_get, list_sync_ts_set,
    list_stocks_all, list_stocks_by_market,
    detail_info_all, detail_info_upsert, detail_info_ts_map,
    detail_kline_date_map,
    detail_klines_insert, detail_remove_stock, detail_sync_atomic, detail_clear_market,
)

# 市场分段 — key 用作 market 字段值（已移除北交所、新三板）
SEGMENTS = {
    'hs_main':  {'label': '沪深A',   'prefix': ('600', '601', '603', '605', '000', '001', '002', '003')},
    'hs_etf':   {'label': '沪深ETF',  'prefix': ('5', '159', '16', '18')},
    'gem':      {'label': '创业板',   'prefix': ('300', '301')},
    'star':     {'label': '科创板',   'prefix': ('688',)},
    'hk_main':  {'label': '港股',     'fs': 'm:116+t:3',       'api': 'eastmoney'},
    'us_main':  {'label': '美股',     'fs': 'm:105,m:106,m:107',       'api': 'eastmoney'},
}

# 各市场交易时间（UTC+8 北京时间），用于判断是否需要更新
MARKET_HOURS = {
    'hs_main':  {'open': (9, 30), 'close': (15, 0)},
    'hs_etf':   {'open': (9, 30), 'close': (15, 0)},
    'gem':      {'open': (9, 30), 'close': (15, 0)},
    'star':     {'open': (9, 30), 'close': (15, 0)},
    'hk_main':  {'open': (9, 30), 'close': (16, 0)},
    'us_main':  {'open': (21, 30), 'close': (4, 0)},  # 美股夏令时 21:30-04:00
}


def _now_ts_str():
    """当前时间的 ISO 格式时间戳字符串"""
    return datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def _code_to_segment(code):
    """代码 → segment key（仅 A 股/ETF 按前缀匹配，港股/美股留空由调用方指定）"""
    for key, seg in SEGMENTS.items():
        if 'prefix' not in seg:
            continue
        for p in seg['prefix']:
            if code.startswith(p):
                return key
    return None


# =========== 拉取股票列表 ===========

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

    if seg_key == 'us_main':
        return _fetch_us_stocks()

    url = 'https://push2delay.eastmoney.com/api/qt/clist/get'
    headers = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://data.eastmoney.com/'}

    is_overseas = seg_key == 'hk_main'
    if seg_key in ('hs_main', 'gem', 'star'):
        fs_filter = 'm:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23'
    elif seg_key in ('hs_etf',):
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
            if price is None or price == '-' or str(price).strip() == '':
                continue
            if is_overseas:
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
                if seg_key in ('hs_etf',):
                    if not any(code.startswith(p) for p in SEGMENTS[seg_key]['prefix']):
                        continue
            all_rows.append((code, name))
        page += 1
        _time.sleep(0.1)
    print(f"[sync] {label}: {len(all_rows)} 只")
    return all_rows


# =========== K 线获取 ===========

def _parse_date(date_str):
    """将 'YYYYMMDD' 字符串转为 date 对象"""
    import datetime as _dt
    return _dt.datetime.strptime(date_str, '%Y%m%d').date()


def _fetch_kline(code, seg_key, period, start_date, end_date):
    """获取 K 线：A股用同花顺 v4 逐年拉取，港股/美股用 Yahoo Finance"""
    import requests as _rq
    import json as _json
    import datetime as _dt

    if seg_key in ('hk_main', 'us_main'):
        return _fetch_kline_yahoo(code, seg_key, period, start_date, end_date)

    global _sync_fail_count

    c = str(code)
    ths_period_code = {'daily': '01', 'weekly': '11', 'monthly': '21'}.get(period, '01')
    current_year = _dt.datetime.now().year

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': 'https://www.10jqka.com.cn/',
    }

    # 增量：last.js（~140条）；全量：v4 逐年拉 5 年
    if start_date and start_date[:4] == str(current_year):
        urls = [f"https://d.10jqka.com.cn/v2/line/hs_{c}/{ths_period_code}/last.js"]
    else:
        urls = [f"https://d.10jqka.com.cn/v4/line/hs_{c}/{ths_period_code}/{y}.js"
                for y in range(current_year, current_year - 5, -1)]

    def _fetch_one(url):
        for attempt in range(3):
            try:
                r = _rq.get(url, headers=headers, timeout=5)
                if r.status_code != 200:
                    if attempt < 2:
                        continue
                    break
                text = r.text
                s = text.find('(') + 1
                e = text.rfind(')')
                if s <= 0 or e <= s:
                    break
                jd = _json.loads(text[s:e])
                return jd.get('data', '')
            except Exception:
                if attempt < 2:
                    continue
        return None

    # 各年并发请求
    from concurrent.futures import ThreadPoolExecutor as _TPE, as_completed as _ac
    all_raw = []
    with _TPE(max_workers=5) as pool:
        futs = {pool.submit(_fetch_one, u): u for u in urls}
        for fut in _ac(futs):
            raw = fut.result()
            if raw:
                all_raw.append(raw)

    if not all_raw:
        return []

    rows = []
    for raw in all_raw:
        for line in raw.split(';'):
            parts = line.split(',')
            if len(parts) < 8:
                continue
            date_str = parts[0]
            if start_date and date_str < start_date:
                continue
            if end_date and date_str > end_date:
                continue
            o = float(parts[1])
            if o <= 0:
                continue
            rows.append((
                code, seg_key, period,
                date_str,
                o,                         # open
                float(parts[2]),           # high
                float(parts[3]),           # low
                float(parts[4]),           # close
                float(parts[5]),           # volume
                float(parts[6]),           # amount
            ))
    return rows


# ---- 同花顺 A 股 K 线 ----

# ---- Yahoo Finance 限流 ----

_yahoo_rate_lock = threading.Lock()
_yahoo_last_req = 0.0
_YAHOO_MIN_INTERVAL = 0.15

_sync_fail_count = 0
_sync_fail_lock = threading.Lock()

# 正在操作的市场集合（按市场粒度互斥，不同市场可并行）
_syncing_markets = set()
_syncing_markets_lock = threading.Lock()


def _fetch_kline_yahoo(code, seg_key, period, start_date, end_date):
    """Yahoo Finance K 线（港股/美股）"""
    global _yahoo_last_req, _sync_fail_count
    import requests as _rq
    import datetime as _dt
    import os as _os

    if seg_key == 'hk_main':
        symbol = str(int(code)).zfill(4) + '.HK'
    else:
        symbol = code

    yh_intv = {'daily': '1d', 'weekly': '1wk', 'monthly': '1mo'}.get(period, '1d')

    for attempt in range(4):
        with _yahoo_rate_lock:
            elapsed = time.time() - _yahoo_last_req
            if elapsed < _YAHOO_MIN_INTERVAL:
                time.sleep(_YAHOO_MIN_INTERVAL - elapsed)
            _yahoo_last_req = time.time()

        _old_no = _os.environ.pop('no_proxy', None)
        _old_NO = _os.environ.pop('NO_PROXY', None)
        try:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=max&interval={yh_intv}"
            r = _rq.get(url, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            }, timeout=15)

            if r.status_code == 404:
                return []

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
    """估算最近的交易日"""
    now = datetime.datetime.now()
    today = now.date()
    wd = today.weekday()

    if wd < 5 and now.hour < 9:
        today = today - datetime.timedelta(days=1)
        wd = today.weekday()

    if wd == 5:
        return (today - datetime.timedelta(days=1)).strftime('%Y%m%d')
    elif wd == 6:
        return (today - datetime.timedelta(days=2)).strftime('%Y%m%d')
    return today.strftime('%Y%m%d')


def _sync_one_stock(code, market, name, kline_date_map, latest_trading, ts_str, periods=('daily', 'weekly', 'monthly'), force_today=False):
    """同步单只股票所有周期的 K 线"""
    if _sync_status.get('cancel'):
        return

    max_date = kline_date_map.get((code, market), None)

    if max_date and max_date >= latest_trading and not force_today:
        return

    # 增量：只差几天时，周线/月线无需重拉
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
        from concurrent.futures import ThreadPoolExecutor as _TPE, as_completed as _ac

        def _fetch_period(p):
            if max_date and max_date != '':
                last = _parse_date(max_date)
                if force_today and max_date == latest_trading:
                    start = max_date
                else:
                    start = (last + datetime.timedelta(days=1)).strftime('%Y%m%d')
            else:
                start = '19900101'
            return _fetch_kline(code, market, p, start, latest_trading)

        all_rows = []
        with _TPE(max_workers=3) as pool:
            futs = {pool.submit(_fetch_period, p): p for p in periods}
            for fut in _ac(futs):
                for r in fut.result():
                    all_rows.append(r)

        if all_rows:
            latest = max(r[3] for r in all_rows)
            detail_sync_atomic(code, market, name, all_rows, latest, ts_str)
            print(f"\r[sync]  ✔ {code} {name} → {latest} (+{len(all_rows)}条)", flush=True)
            return True
        else:
            if max_date:
                detail_info_upsert(code, market, name or code, ts_str)
                print(f"\r[sync]  ~ {code} {name} 无新数据 (已有 {max_date})", flush=True)
                return True
            else:
                print(f"\r[sync]  ✘ {code} {name} API 返回空 (periods={periods})", flush=True)
                return False
    except Exception as _e:
        print(f"\n[sync] !!! _sync_one_stock 异常 [{code}]: {type(_e).__name__}: {_e}", flush=True)
        return False


# =========== 清理退市 ===========

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


# =========== 加载（初始化新市场） ===========

_sync_status = {'running': False, 'label': '', 'total': 0, 'done': 0, 'phase': '', 'cancel': False, 'seg_key': None, 'task_type': None, 'success_count': 0, 'fail_count': 0}

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

    with _syncing_markets_lock:
        if '*' in _syncing_markets or seg_key in _syncing_markets:
            return {'success': False, 'error': '该市场正在操作中'}
        _syncing_markets.add(seg_key)

    _sync_status['running'] = True
    _sync_status['label'] = SEGMENTS[seg_key]['label']
    _sync_status['seg_key'] = seg_key
    _sync_status['task_type'] = 'init'
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

        if _sync_status.get('cancel'):
            _sync_status['running'] = False
            _sync_status['phase'] = 'cancelled'
            _sync_status['cancel'] = False
            print(f"[sync] {label} 加载已被终止")
            return

        list_replace_market(seg_key, rows)
        print(f"[sync] {label} 股票列表已写入: {len(rows)} 只")

        if _sync_status.get('cancel'):
            list_replace_market(seg_key, [])
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
        kline_date_map = {}
        latest_trading = _latest_possible_trading_day()
        ts_str = _now_ts_str()
        cancelled = False
        success_count = 0
        fail_count = 0
        with ThreadPoolExecutor(max_workers=4) as pool:
            futs = {pool.submit(_sync_one_stock, s[0], s[1], s[2], kline_date_map, latest_trading, ts_str): s for s in stocks}
            for fut in as_completed(futs):
                if _sync_status.get('cancel'):
                    cancelled = True
                    break
                try:
                    if fut.result():
                        success_count += 1
                    else:
                        fail_count += 1
                except Exception:
                    fail_count += 1
                _sync_status['done'] += 1
                step = 50
                if _sync_status['done'] % step == 0 or _sync_status['done'] == len(stocks):
                    pct = _sync_status['done'] / len(stocks) * 100
                    el = time.time() - t0
                    eta = el / _sync_status['done'] * (len(stocks) - _sync_status['done']) if _sync_status['done'] > 0 else 0
                    bar = '█' * int(30 * _sync_status['done'] / len(stocks)) + '░' * (30 - int(30 * _sync_status['done'] / len(stocks)))
                    print(f"\r[sync] K线 [{bar}] {pct:5.1f}% {_sync_status['done']}/{len(stocks)}  耗时 {el:.0f}s 预计剩余 {eta:.0f}s", end='', flush=True)
        print()

        if cancelled:
            detail_clear_market(seg_key)
            list_replace_market(seg_key, [])
            _sync_status['running'] = False
            _sync_status['phase'] = 'cancelled'
            _sync_status['cancel'] = False
            print(f"[sync] {label} K线同步已被终止，数据已回滚")
            return

        _cleanup_delisted()
        if fail_count == 0:
            list_sync_ts_set(seg_key, _now_ts_str())
        else:
            print(f"[sync] {label} 有 {fail_count} 只股票拉取失败，本次不更新 sync_ts，下次更新将重试")
        _sync_status['success_count'] = success_count
        _sync_status['fail_count'] = fail_count
        el = time.time() - t0
        print(f"[sync] {label} 初始化完成: 成功 {success_count} 只, 失败 {fail_count} 只, 耗时 {el:.0f}s")
    finally:
        if _sync_status['phase'] not in ('cancelled', 'error'):
            _sync_status['running'] = False
            _sync_status['phase'] = 'done'
        with _syncing_markets_lock:
            _syncing_markets.discard(seg_key)


# =========== 更新（增量同步已有市场） ===========

def _need_update(seg_key):
    """根据 stocks.sync_ts 和当前时间判断是否需要更新K线数据

    返回值:
        True  → 需要更新
        False → 数据已是最新
    """
    last_ts_str = list_sync_ts_get(seg_key)
    if not last_ts_str:
        # 没有时间戳记录，需要更新
        return True

    try:
        last_ts = datetime.datetime.strptime(last_ts_str, '%Y-%m-%d %H:%M:%S')
    except ValueError:
        return True

    now = datetime.datetime.now()

    # 更新时间比记录时间早 → 数据是最新的
    if now <= last_ts:
        return False

    seg_hours = MARKET_HOURS.get(seg_key)
    if not seg_hours:
        # 未知市场，保守地需要更新
        return True

    open_h, open_m = seg_hours['open']
    close_h, close_m = seg_hours['close']

    # 美股跨日：close 小于 open 表示次日收盘
    is_cross_day = close_h < open_h or (close_h == open_h and close_m < open_m)

    def _to_minutes(h, m):
        return h * 60 + m

    open_min = _to_minutes(open_h, open_m)
    close_min = _to_minutes(close_h, close_m)

    def _is_before_open(dt):
        """判断时间是否在开盘前"""
        dt_min = _to_minutes(dt.hour, dt.minute)
        if is_cross_day:
            # 美股：开盘在晚上，close 在次日凌晨
            # 开盘前 = dt_min < open_min (晚上开盘前)
            return dt_min < open_min
        else:
            return dt_min < open_min

    def _is_after_close(dt):
        """判断时间是否在收盘后"""
        dt_min = _to_minutes(dt.hour, dt.minute)
        if is_cross_day:
            # 美股收盘在次日凌晨: close_min 如 4:00 = 240
            # 收盘后 = dt_min >= close_min 且 dt_min < open_min（次日凌晨到当晚开盘前）
            return dt_min >= close_min and dt_min < open_min
        else:
            return dt_min >= close_min

    def _is_trading_hours(dt):
        """判断时间是否在交易时段内（含收盘时刻）"""
        dt_min = _to_minutes(dt.hour, dt.minute)
        if is_cross_day:
            # 交易时段 = open_min..24:00 或 0:00..close_min
            return dt_min >= open_min or dt_min < close_min
        else:
            return open_min <= dt_min < close_min

    # 计算两个时间之间排除周末的天数差异
    def _trading_days_between(d1, d2):
        """计算 d1 到 d2 之间的交易日数（排除周末），不含 d2 当天"""
        count = 0
        cur = d1.date()
        end = d2.date()
        while cur < end:
            if cur.weekday() < 5:
                count += 1
            cur += datetime.timedelta(days=1)
        return count

    trading_days_gap = _trading_days_between(last_ts, now)

    # 跨了1个交易日以上 → 肯定有新K线数据需要更新
    if trading_days_gap >= 1:
        return True

    # 同一天内（或跨0个交易日）
    # 情况1: 记录时间在开盘前，现在也在开盘前 → 没有新K线
    if _is_before_open(last_ts) and _is_before_open(now):
        return False

    # 情况2: 记录时间在交易时段内 → 当天K线数据还在变化，需要更新
    if _is_trading_hours(last_ts):
        return True

    # 情况3: 记录时间在收盘后
    if _is_after_close(last_ts):
        if _is_before_open(now):
            # 收盘后到次日开盘前 → 没有新K线
            return False
        else:
            # 收盘后，但现在已到开盘或交易时段 → 可能有新K线
            return True

    # 其他情况保守更新
    return True


def update_market(seg_key):
    """增量更新指定市场的K线数据"""
    global _sync_status
    if seg_key not in SEGMENTS:
        return {'success': False, 'error': '无效的市场分段'}

    if seg_key not in list_markets():
        return {'success': False, 'error': '该市场未加载，请先加载'}

    if _sync_status['running']:
        return {'success': False, 'error': '已有同步任务运行中'}

    # 检查是否需要更新（必须在加锁之前，避免 false 时锁未释放）
    if not _need_update(seg_key):
        return {'success': False, 'error': '数据已是最新，无需更新'}

    with _syncing_markets_lock:
        if '*' in _syncing_markets or seg_key in _syncing_markets:
            return {'success': False, 'error': '该市场正在操作中'}
        _syncing_markets.add(seg_key)

    _sync_status['running'] = True
    _sync_status['label'] = SEGMENTS[seg_key]['label']
    _sync_status['seg_key'] = seg_key
    _sync_status['task_type'] = 'update'
    threading.Thread(target=_run_update, args=(seg_key,), daemon=True).start()
    return {'success': True, 'message': '更新已启动'}


def _list_need_refresh(seg_key):
    """根据 stocks.sync_ts 判断股票列表是否需要重新拉取

    规则：如果 stocks.sync_ts 是在"最近一次该市场开盘时间"或之后，
    那么列表仍是新的（在该市场下一次开盘前都不会有新上市/退市变化）。
    否则列表可能过时，需要重新拉取。
    """
    last_ts_str = list_sync_ts_get(seg_key)
    if not last_ts_str:
        # 没有时间戳记录，需要拉取
        return True

    try:
        last_ts = datetime.datetime.strptime(last_ts_str, '%Y-%m-%d %H:%M:%S')
    except ValueError:
        return True

    seg_hours = MARKET_HOURS.get(seg_key)
    if not seg_hours:
        # 未知市场，保守地需要拉取
        return True

    open_h, open_m = seg_hours['open']
    is_cross_day = seg_hours['close'][0] < open_h or (seg_hours['close'][0] == open_h and seg_hours['close'][1] < open_m)

    def _to_minutes(h, m):
        return h * 60 + m
    open_min = _to_minutes(open_h, open_m)

    def _is_in_or_after_open(dt):
        """判断时间是否在开盘时间或之后（美股考虑跨日）"""
        dt_min = _to_minutes(dt.hour, dt.minute)
        if is_cross_day:
            # 美股：开盘在晚上 21:30，dt_min >= open_min 即"已开盘"或之后
            return dt_min >= open_min
        else:
            return dt_min >= open_min

    # 找到"最近一次该市场开盘"的时间点
    now = datetime.datetime.now()
    last_open_dt = None

    if is_cross_day:
        # 美股：开盘在晚上
        # 找最近一次"今天或昨天的晚上 21:30"
        # 如果当前时间在开盘前（早上到晚上开盘前），最近开盘是"昨天的 21:30"
        # 如果当前时间在开盘后（21:30 后），最近开盘是"今天的 21:30"
        if now.hour * 60 + now.minute < open_min:
            last_open_date = now.date() - datetime.timedelta(days=1)
        else:
            last_open_date = now.date()
        # 跳过周末：最近一次开盘日
        while last_open_date.weekday() >= 5:
            last_open_date -= datetime.timedelta(days=1)
        last_open_dt = datetime.datetime.combine(last_open_date, datetime.time(open_h, open_m))
    else:
        # A股 / 港股：开盘在白天
        # 找最近一次交易日的 9:30
        last_open_date = now.date()
        if now.hour * 60 + now.minute < open_min:
            # 还没到开盘，最近开盘是"昨天的 9:30"
            last_open_date = now.date() - datetime.timedelta(days=1)
        # 跳过周末
        while last_open_date.weekday() >= 5:
            last_open_date -= datetime.timedelta(days=1)
        last_open_dt = datetime.datetime.combine(last_open_date, datetime.time(open_h, open_m))

    # stocks.sync_ts >= 最近开盘时间 → 列表仍是新的
    return last_ts < last_open_dt


def _run_update(seg_key):
    global _sync_status
    try:
        label = SEGMENTS[seg_key]['label']
        _sync_status['cancel'] = False
        print(f"[sync] 更新: {label}")

        latest_trading = _latest_possible_trading_day()
        kline_date_map = detail_kline_date_map()

        # 第一步：判断股票列表是否需要重拉
        need_refresh_list = _list_need_refresh(seg_key)
        last_ts_str = list_sync_ts_get(seg_key)
        print(f"[sync] {label} sync_ts: {last_ts_str or '无'}, 列表{'需要' if need_refresh_list else '无需'}重拉")

        if need_refresh_list:
            _sync_status['phase'] = 'list'
            rows = _fetch_stocks_by_segment(seg_key)
            if rows is None:
                print(f"[sync] {label} 列表拉取失败")
                _sync_status['running'] = False
                _sync_status['phase'] = 'error'
                _sync_status['error'] = f'{label} 列表拉取失败'
                return

            if _sync_status.get('cancel'):
                # 中途终止：stocks 表未更新，下次继续
                _sync_status['running'] = False
                _sync_status['phase'] = 'cancelled'
                _sync_status['cancel'] = False
                print(f"[sync] {label} 更新已被终止")
                return

            list_replace_market(seg_key, rows)
            print(f"[sync] {label} 股票列表已更新: {len(rows)} 只")
        else:
            existing_stocks = list_stocks_by_market().get(seg_key, {})
            rows = [(code, name) for code, name in existing_stocks.items()]

        # 第二步：筛选需要更新 K 线的个股
        stock_list = [(code, seg_key, name) for code, name in rows]
        to_update = [s for s in stock_list
                     if not kline_date_map.get((s[0], s[1]), '') or
                        kline_date_map.get((s[0], s[1]), '') < latest_trading]

        if not to_update:
            # 全部个股已是最新 → 写入市场 sync_ts
            print(f"[sync] {label} K线全部已是最新 ({len(stock_list)} 只)，无需拉取")
            list_sync_ts_set(seg_key, _now_ts_str())
            _cleanup_delisted()
            _sync_status['running'] = False
            _sync_status['phase'] = 'done'
            return

        # 第三步：增量同步 K 线（每只线程内单独写自己的 stock_info 时间戳）
        _sync_status['total'] = len(stock_list)
        _sync_status['done'] = 0
        _sync_status['phase'] = 'kline'
        global _sync_fail_count
        _sync_fail_count = 0

        skipped = len(stock_list) - len(to_update)
        print(f"[sync] {label} 增量同步 K 线 (已是最新: {skipped} 只，需要更新: {len(to_update)} 只，4 线程)...")

        t0 = time.time()
        ts_str = _now_ts_str()
        cancelled = False
        success_count = 0
        fail_count = 0
        with ThreadPoolExecutor(max_workers=4) as pool:
            futs = {pool.submit(_sync_one_stock, s[0], s[1], s[2], kline_date_map, latest_trading, ts_str): s for s in to_update}
            for fut in as_completed(futs):
                if _sync_status.get('cancel'):
                    cancelled = True
                    break
                try:
                    if fut.result():
                        success_count += 1
                    else:
                        fail_count += 1
                except Exception:
                    fail_count += 1
                _sync_status['done'] += 1
                if _sync_status['done'] <= 4 or _sync_status['done'] % 10 == 0 or _sync_status['done'] == len(to_update):
                    pct = _sync_status['done'] / len(to_update) * 100
                    el = time.time() - t0
                    eta = el / _sync_status['done'] * (len(to_update) - _sync_status['done']) if _sync_status['done'] > 0 else 0
                    bar = '█' * int(30 * _sync_status['done'] / len(to_update)) + '░' * (30 - int(30 * _sync_status['done'] / len(to_update)))
                    print(f"\r[sync] K线 [{bar}] {pct:5.1f}% {_sync_status['done']}/{len(to_update)}  耗时 {el:.0f}s 预计剩余 {eta:.0f}s", end='', flush=True)
        print()

        if cancelled:
            # 中途终止：已完成个股的 kline 已写入，stocks.sync_ts 未写
            # 下次更新时会跳过已完成的个股，续传剩余的
            _sync_status['running'] = False
            _sync_status['phase'] = 'cancelled'
            _sync_status['cancel'] = False
            print(f"[sync] {label} 更新已被终止（已完成的数据保留，下次续传）")
            return

        # 第四步：全部个股更新完毕 → 写入市场 sync_ts（仅全部成功时）
        if fail_count == 0:
            list_sync_ts_set(seg_key, _now_ts_str())
        else:
            print(f"[sync] {label} 有 {fail_count} 只股票拉取失败，本次不更新 sync_ts，下次更新将重试")

        # 第五步：清理退市
        _cleanup_delisted()
        _sync_status['success_count'] = success_count
        _sync_status['fail_count'] = fail_count

        el = time.time() - t0
        print(f"[sync] {label} 更新完成: 成功 {success_count} 只, 失败 {fail_count} 只, 耗时 {el:.0f}s")
    finally:
        if _sync_status['phase'] not in ('cancelled', 'error'):
            _sync_status['running'] = False
            _sync_status['phase'] = 'done'
        with _syncing_markets_lock:
            _syncing_markets.discard(seg_key)


# =========== 通用状态 ===========

def get_init_status():
    return dict(_sync_status)


def cancel_init():
    """终止当前运行中的同步/更新任务"""
    global _sync_status
    if not _sync_status['running']:
        return {'success': False, 'error': '没有运行中的任务'}
    if _sync_status.get('cancel'):
        return {'success': False, 'error': '正在终止中，请稍候'}
    _sync_status['cancel'] = True
    label = _sync_status.get('label', '')
    task_type = _sync_status.get('task_type', '')
    verb = '更新' if task_type == 'update' else '加载'
    return {'success': True, 'message': '正在终止' + (label + ' ' if label else '') + f'数据{verb}...'}


def get_segments_info():
    """返回各分段状态"""
    markets = list_markets()
    result = []
    for key, seg in SEGMENTS.items():
        synced = key in markets
        ts = list_sync_ts_get(key) if synced else None
        count = 0
        if synced:
            import sqlite3 as _sq, os as _os2
            conn_detail = _sq.connect(
                _os2.path.join(_os2.path.dirname(_os2.path.dirname(__file__)), 'data', 'stock_detail_list.db'))
            count = conn_detail.execute('SELECT COUNT(DISTINCT code) FROM klines WHERE market=?', (key,)).fetchone()[0]
            conn_detail.close()
        result.append({'key': key, 'label': seg['label'], 'synced': synced, 'sync_ts': ts, 'kline_count': count})
    return {
        'segments': result,
        'init_running': _sync_status.get('running', False),
        'init_seg_key': _sync_status.get('seg_key'),
        'init_phase': _sync_status.get('phase'),
        'init_task_type': _sync_status.get('task_type'),
    }


# =========== 清库 ===========

def clear_market(seg_key):
    """清除指定市场的所有数据（列表 + K线 + 元信息）"""
    if seg_key not in SEGMENTS:
        return {'success': False, 'error': '无效的市场分段'}
    if seg_key not in list_markets():
        return {'success': False, 'error': '该市场无数据可清除'}

    with _syncing_markets_lock:
        if '*' in _syncing_markets or seg_key in _syncing_markets:
            return {'success': False, 'error': '正在操作中，请先终止后再清库'}

    label = SEGMENTS[seg_key]['label']
    print(f"[sync] 清除 {label} 数据...")

    detail_clear_market(seg_key)
    list_replace_market(seg_key, [])

    print(f"[sync] {label} 数据已清除")
    return {'success': True, 'message': f'{label} 数据已清除'}
