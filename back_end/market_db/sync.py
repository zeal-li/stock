"""全市场数据同步
加载（初始化）：
  1. 拉取股票列表 → 写入 market_stock_list
  2. 全量同步 K 线 → 写入 stock_klines + stock_info
  3. 清理退市
  4. 更新 stock_market.sync_ts

更新（增量）：
  1. 检查 stock_market.sync_ts，判断是否需要更新
  2. 拉取最新股票列表 → 替换 market_stock_list
  3. 增量同步 K 线（per-period 独立判断）
  4. 更新 stock_market.sync_ts
  5. 清理退市
"""
import datetime
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from .db import (
    market_all, market_sync_ts_get, market_sync_ts_set,
    market_list_ts_get, market_list_ts_set, market_remove,
    stock_list_all, stock_list_by_market, stock_list_replace_market,
    stock_info_all, stock_info_kline_maps, stock_info_remove, stock_info_clear_market,
    stock_info_sync_atomic, klines_get, klines_count_market,
)
from common.utils import (
    MARKET_HOURS, is_before_open, is_after_close, is_trading_hours,
    is_cross_day, get_market_hours,
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
    filtered_by_cap = 0
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
                    'fields': 'f2,f12,f14,f20',
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
                    # 过滤市值小于10亿的ETF
                    try:
                        cap = row.get('f20')
                        if cap is None or cap == '-' or str(cap).strip() == '':
                            filtered_by_cap += 1
                            continue
                        if float(cap) < 1_000_000_000:
                            filtered_by_cap += 1
                            continue
                    except (ValueError, TypeError):
                        filtered_by_cap += 1
                        continue
            all_rows.append((code, name))
        page += 1
        _time.sleep(0.1)
    if filtered_by_cap > 0 and seg_key == 'hs_etf':
        print(f"[sync] {label}: {len(all_rows)} 只 (过滤掉市值<10亿: {filtered_by_cap} 只)")
    else:
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

    # 同花顺前缀：按交易所区分
    # 上交所：60xxxx/688xxx(沪A/科创), 51xxxx/56xxxx/58xxxx(沪ETF/基), 11xxxx(沪债), 9xxxxx(沪B)
    # 深交所：00xxxx~003xxx(深A), 30xxxx/301xxx(创业), 159xxx/16xxxx/18xxxx(深ETF/基), 12xxxx(深债)
    if c[0] == '6' or c.startswith(('5', '11', '9')):
        ths_prefix = 'sh'
    else:
        ths_prefix = 'sz'

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': 'https://www.10jqka.com.cn/',
    }

    # 4线程×3周期×2年份=24并发，默认连接池10不够，建Session扩到30
    _session = _rq.Session()
    _adapter = _rq.adapters.HTTPAdapter(pool_connections=30, pool_maxsize=30)
    _session.mount('https://', _adapter)
    _session.mount('http://', _adapter)

    # 全量：v4 逐年拉 5 年；增量：v4 只拉当年
    if start_date and start_date[:4] == str(current_year):
        urls = [f"https://d.10jqka.com.cn/v4/line/{ths_prefix}_{c}/{ths_period_code}/{current_year}.js"]
    else:
        urls = [f"https://d.10jqka.com.cn/v4/line/{ths_prefix}_{c}/{ths_period_code}/{y}.js"
                for y in range(current_year, current_year - 5, -1)]

    def _fetch_one(url):
        for attempt in range(3):
            try:
                r = _session.get(url, headers=headers, timeout=5)
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

    # 各年2并发请求（4×3×2=24并发，同花顺可承受）
    from concurrent.futures import ThreadPoolExecutor as _TPE, as_completed as _ac
    all_raw = []
    with _TPE(max_workers=2) as pool:
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
            o = float(parts[1]) if parts[1] else 0
            h = float(parts[2]) if parts[2] else 0
            l = float(parts[3]) if parts[3] else 0
            c = float(parts[4]) if parts[4] else 0
            if c <= 0:
                continue
            # 开/高/低为空或为0时，用收盘价补上
            if o <= 0:
                o = c
            if h <= 0:
                h = c
            if l <= 0:
                l = c
            volume = float(parts[5]) if parts[5] else 0
            amount = float(parts[6]) if parts[6] else 0
            turnover = round(float(parts[7]) if parts[7] else 0, 2)
            rows.append((
                code, seg_key, period,
                date_str,
                o,
                h,
                l,
                c,
                volume,
                amount,
                turnover,
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
                    None,
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


def _sync_one_stock(code, market, name, daily_map, weekly_map, monthly_map, latest_trading, ts_str, force_today=False):
    """同步单只股票 K 线 — per-period 独立判断是否需要拉取"""
    if _sync_status.get('cancel'):
        return

    # 判断每个周期是否需要更新
    def _needs(ts):
        if not ts:
            return True
        date = ts[:10].replace('-', '')  # "2026-06-13" → "20260613"
        return date < latest_trading

    periods = []
    if _needs(daily_map.get((code, market))) or force_today:
        periods.append('daily')
    if _needs(weekly_map.get((code, market))) or (force_today and not periods):
        periods.append('weekly')
    if _needs(monthly_map.get((code, market))) or (force_today and not periods):
        periods.append('monthly')

    if not periods and not force_today:
        return

    try:
        from concurrent.futures import ThreadPoolExecutor as _TPE, as_completed as _ac

        def _fetch_period(p):
            ts = {  # per-period 旧时间戳
                'daily': daily_map.get((code, market)),
                'weekly': weekly_map.get((code, market)),
                'monthly': monthly_map.get((code, market)),
            }.get(p)
            if ts:
                last_date = _parse_date(ts[:10].replace('-', ''))
                if force_today and ts[:10].replace('-', '') == latest_trading:
                    start = latest_trading
                else:
                    start = (last_date + datetime.timedelta(days=1)).strftime('%Y%m%d')
            else:
                start = '19900101'
            return _fetch_kline(code, market, p, start, latest_trading)

        all_rows = []
        synced_periods = set()
        with _TPE(max_workers=len(periods)) as pool:
            futs = {pool.submit(_fetch_period, p): p for p in periods}
            for fut in _ac(futs):
                p = futs[fut]
                rows = fut.result()
                if rows:
                    synced_periods.add(p)
                    for r in rows:
                        all_rows.append(r)

        if all_rows:
            # 原子写入（拿到多少写多少，不丢进度）
            period_dates = {p: ts_str for p in synced_periods}
            stock_info_sync_atomic(code, market, name, all_rows, period_dates)
            if synced_periods == set(periods):
                # 所有需要的周期都拉到了 → 完整成功
                print(f"\r[sync]  ✔ {code} {name} → +{len(all_rows)}条 [{','.join(sorted(synced_periods))}]", flush=True)
                return True
            else:
                # 部分周期拉到，部分没拉到 → 已写入成功的，失败的等下次重试
                missing = [p for p in periods if p not in synced_periods]
                print(f"\r[sync]  △ {code} {name} 部分完成 +{len(all_rows)}条 [{','.join(sorted(synced_periods))}] 缺[{','.join(missing)}]", flush=True)
                return 'partial'
        else:
            existing_any = daily_map.get((code, market)) or weekly_map.get((code, market)) or monthly_map.get((code, market))
            if existing_any:
                max_date = max(filter(None, [
                    (daily_map.get((code, market)) or '')[:10].replace('-', ''),
                    (weekly_map.get((code, market)) or '')[:10].replace('-', ''),
                    (monthly_map.get((code, market)) or '')[:10].replace('-', ''),
                ]), default='')
                if max_date:
                    gap = (_parse_date(latest_trading) - _parse_date(max_date)).days
                    if gap > 30:
                        print(f"\r[sync]  ~ {code} {name} 可能已退市 (最新数据 {max_date}, 距今 {gap} 天)", flush=True)
                        return 'inactive'
                print(f"\r[sync]  ~ {code} {name} 无新数据", flush=True)
                return None
            else:
                print(f"\r[sync]  ✘ {code} {name} API 返回空 (periods={periods})", flush=True)
                return False
    except Exception as _e:
        print(f"\n[sync] !!! _sync_one_stock 异常 [{code}]: {type(_e).__name__}: {_e}", flush=True)
        raise


# =========== 清理退市 ===========

def _cleanup_delisted():
    active = set((s[0], s[1]) for s in stock_list_all())
    if not active:
        return

    detail_stocks = stock_info_all()
    delisted = [(s[0], s[1]) for s in detail_stocks if (s[0], s[1]) not in active]
    if not delisted:
        print("[sync] 无退市股票")
        return

    for code, market in delisted:
        stock_info_remove(code, market)
    print(f"[sync] 清理退市股票: {len(delisted)} 只")


# =========== 加载（初始化新市场） ===========

_sync_status = {'running': False, 'label': '', 'total': 0, 'done': 0, 'phase': '', 'cancel': False, 'seg_key': None, 'task_type': None, 'success_count': 0, 'no_data_count': 0, 'inactive_count': 0, 'api_empty_count': 0, 'exception_count': 0}

def init_segment(seg_key):
    """初始化一个市场分段：拉取股票列表 + 全量同步 K 线"""
    global _sync_status
    if seg_key not in SEGMENTS:
        return {'success': False, 'error': '无效的市场分段'}

    if seg_key in market_all():
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

        stock_list_replace_market(seg_key, rows)
        market_list_ts_set(seg_key, _now_ts_str())
        print(f"[sync] {label} 股票列表已写入: {len(rows)} 只")

        if _sync_status.get('cancel'):
            stock_list_replace_market(seg_key, [])
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
        daily_map = {}; weekly_map = {}; monthly_map = {}  # 新市场全空
        latest_trading = _latest_possible_trading_day()
        ts_str = _now_ts_str()
        cancelled = False
        success_count = 0
        no_data_count = 0
        inactive_count = 0
        api_empty_count = 0
        exception_count = 0
        partial_count = 0
        with ThreadPoolExecutor(max_workers=4) as pool:
            futs = {pool.submit(_sync_one_stock, s[0], s[1], s[2], daily_map, weekly_map, monthly_map, latest_trading, ts_str): s for s in stocks}
            for fut in as_completed(futs):
                if _sync_status.get('cancel'):
                    cancelled = True
                    break
                try:
                    result = fut.result()
                    if result is None:
                        no_data_count += 1
                    elif result == 'inactive':
                        inactive_count += 1
                    elif result == 'partial':
                        partial_count += 1
                    elif result:
                        success_count += 1
                    else:
                        api_empty_count += 1
                except Exception:
                    exception_count += 1
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
            stock_info_clear_market(seg_key)
            stock_list_replace_market(seg_key, [])
            _sync_status['running'] = False
            _sync_status['phase'] = 'cancelled'
            _sync_status['cancel'] = False
            print(f"[sync] {label} K线同步已被终止，数据已回滚")
            return

        _cleanup_delisted()
        fail_count = api_empty_count + exception_count + partial_count
        if fail_count == 0 and no_data_count == 0:
            market_sync_ts_set(seg_key, _now_ts_str())
        else:
            reasons = []
            if exception_count > 0:
                reasons.append(f"{exception_count} 只网络异常")
            if api_empty_count > 0:
                reasons.append(f"{api_empty_count} 只API返回空")
            if partial_count > 0:
                reasons.append(f"{partial_count} 只部分完成")
            if no_data_count > 0:
                reasons.append(f"{no_data_count} 只无新数据")
            print(f"[sync] {label} 有 {', '.join(reasons)}，本次不更新 sync_ts，下次更新将重试")
        _sync_status['success_count'] = success_count
        _sync_status['no_data_count'] = no_data_count
        _sync_status['inactive_count'] = inactive_count
        _sync_status['api_empty_count'] = api_empty_count
        _sync_status['exception_count'] = exception_count
        _sync_status['partial_count'] = partial_count
        el = time.time() - t0
        print(f"[sync] {label} 初始化完成: 拉取成功 {success_count} 只, 部分完成 {partial_count} 只, 无新数据 {no_data_count} 只, 可能已退市 {inactive_count} 只, API返回空 {api_empty_count} 只, 网络异常 {exception_count} 只, 耗时 {el:.0f}s")
    finally:
        if _sync_status['phase'] not in ('cancelled', 'error'):
            _sync_status['running'] = False
            _sync_status['phase'] = 'done'
        with _syncing_markets_lock:
            _syncing_markets.discard(seg_key)


# =========== 更新（增量同步已有市场） ===========

def _need_update(seg_key):
    """根据 stock_market.sync_ts 和当前时间判断是否需要更新K线数据

    返回值:
        True  → 需要更新
        False → 数据已是最新
    """
    last_ts_str = market_sync_ts_get(seg_key)
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
    _is_cross_day = is_cross_day(open_h, open_m, close_h, close_m)

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
    if is_before_open(last_ts, open_h, open_m) and is_before_open(now, open_h, open_m):
        return False

    # 情况2: 记录时间在交易时段内 → 当天K线数据还在变化，需要更新
    if is_trading_hours(last_ts, open_h, open_m, close_h, close_m, _is_cross_day):
        return True

    # 情况3: 记录时间在收盘后
    if is_after_close(last_ts, close_h, close_m, open_h, open_m, _is_cross_day):
        if is_before_open(now, open_h, open_m):
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

    if seg_key not in market_all():
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
    """根据 market_list_ts 判断股票列表是否需要重新拉取"""
    last_ts_str = market_list_ts_get(seg_key)
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
    close_h, close_m = seg_hours['close']
    _is_cross_day = is_cross_day(open_h, open_m, close_h, close_m)

    # 找到"最近一次该市场开盘"的时间点
    now = datetime.datetime.now()
    from common.utils import to_minutes
    open_min = to_minutes(open_h, open_m)

    if _is_cross_day:
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
        daily_map, weekly_map, monthly_map = stock_info_kline_maps()

        # 第一步：判断股票列表是否需要重拉
        need_refresh_list = _list_need_refresh(seg_key)
        list_ts_str = market_list_ts_get(seg_key)
        kline_ts_str = market_sync_ts_get(seg_key)
        print(f"[sync] {label} 列表时间: {list_ts_str or '无'}, K线时间: {kline_ts_str or '无'}, 列表{'需要' if need_refresh_list else '无需'}重拉")

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
                _sync_status['running'] = False
                _sync_status['phase'] = 'cancelled'
                _sync_status['cancel'] = False
                print(f"[sync] {label} 更新已被终止")
                return

            stock_list_replace_market(seg_key, rows)
            market_list_ts_set(seg_key, _now_ts_str())
            print(f"[sync] {label} 股票列表已更新: {len(rows)} 只")
        else:
            existing_stocks = stock_list_by_market().get(seg_key, {})
            rows = [(code, name) for code, name in existing_stocks.items()]

        # 第二步：筛选需要更新 K 线的个股（任一周期落后于最新交易日就需要更新）
        stock_list = [(code, seg_key, name) for code, name in rows]

        def _needs_any_update(code, market):
            for m in [daily_map, weekly_map, monthly_map]:
                ts = m.get((code, market))
                if not ts:
                    return True
                if ts[:10].replace('-', '') < latest_trading:
                    return True
            return False

        to_update = [s for s in stock_list if _needs_any_update(s[0], s[1])]

        if not to_update:
            print(f"[sync] {label} K线全部已是最新 ({len(stock_list)} 只)，无需拉取")
            market_sync_ts_set(seg_key, _now_ts_str())
            _cleanup_delisted()
            _sync_status['running'] = False
            _sync_status['phase'] = 'done'
            return

        # 第三步：增量同步 K 线（per-period 独立判断）
        _sync_status['total'] = len(to_update)
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
        no_data_count = 0
        inactive_count = 0
        api_empty_count = 0
        exception_count = 0
        partial_count = 0
        with ThreadPoolExecutor(max_workers=4) as pool:
            futs = {pool.submit(_sync_one_stock, s[0], s[1], s[2], daily_map, weekly_map, monthly_map, latest_trading, ts_str): s for s in to_update}
            for fut in as_completed(futs):
                if _sync_status.get('cancel'):
                    cancelled = True
                    break
                try:
                    result = fut.result()
                    if result is None:
                        no_data_count += 1
                    elif result == 'inactive':
                        inactive_count += 1
                    elif result == 'partial':
                        partial_count += 1
                    elif result:
                        success_count += 1
                    else:
                        api_empty_count += 1
                except Exception:
                    exception_count += 1
                _sync_status['done'] += 1
                if _sync_status['done'] <= 4 or _sync_status['done'] % 10 == 0 or _sync_status['done'] == len(to_update):
                    pct = _sync_status['done'] / len(to_update) * 100
                    el = time.time() - t0
                    eta = el / _sync_status['done'] * (len(to_update) - _sync_status['done']) if _sync_status['done'] > 0 else 0
                    bar = '█' * int(30 * _sync_status['done'] / len(to_update)) + '░' * (30 - int(30 * _sync_status['done'] / len(to_update)))
                    print(f"\r[sync] K线 [{bar}] {pct:5.1f}% {_sync_status['done']}/{len(to_update)}  耗时 {el:.0f}s 预计剩余 {eta:.0f}s", end='', flush=True)
        print()

        if cancelled:
            _sync_status['running'] = False
            _sync_status['phase'] = 'cancelled'
            _sync_status['cancel'] = False
            print(f"[sync] {label} 更新已被终止（已完成的数据保留，下次续传）")
            return

        # 第四步：全部个股更新完毕 → 写入市场 sync_ts（仅全部拉取成功时）
        fail_count = api_empty_count + exception_count + partial_count
        if fail_count == 0 and no_data_count == 0:
            market_sync_ts_set(seg_key, _now_ts_str())
        else:
            reasons = []
            if exception_count > 0:
                reasons.append(f"{exception_count} 只网络异常")
            if api_empty_count > 0:
                reasons.append(f"{api_empty_count} 只API返回空")
            if partial_count > 0:
                reasons.append(f"{partial_count} 只部分完成")
            if no_data_count > 0:
                reasons.append(f"{no_data_count} 只无新数据")
            print(f"[sync] {label} 有 {', '.join(reasons)}，本次不更新 sync_ts，下次更新将重试")

        # 第五步：清理退市
        _cleanup_delisted()
        _sync_status['success_count'] = success_count
        _sync_status['no_data_count'] = no_data_count
        _sync_status['inactive_count'] = inactive_count
        _sync_status['api_empty_count'] = api_empty_count
        _sync_status['exception_count'] = exception_count
        _sync_status['partial_count'] = partial_count

        el = time.time() - t0
        print(f"[sync] {label} 更新完成: 拉取成功 {success_count} 只, 部分完成 {partial_count} 只, 无新数据 {no_data_count} 只, 可能已退市 {inactive_count} 只, API返回空 {api_empty_count} 只, 网络异常 {exception_count} 只, 耗时 {el:.0f}s")
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
    markets = market_all()
    result = []
    for key, seg in SEGMENTS.items():
        synced = key in markets
        ts = market_sync_ts_get(key) if synced else None
        count = klines_count_market(key) if synced else 0
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
    if seg_key not in market_all():
        return {'success': False, 'error': '该市场无数据可清除'}

    with _syncing_markets_lock:
        if '*' in _syncing_markets or seg_key in _syncing_markets:
            return {'success': False, 'error': '正在操作中，请先终止后再清库'}

    label = SEGMENTS[seg_key]['label']
    print(f"[sync] 清除 {label} 数据...")

    stock_info_clear_market(seg_key)
    stock_list_replace_market(seg_key, [])
    market_remove(seg_key)

    print(f"[sync] {label} 数据已清除")
    return {'success': True, 'message': f'{label} 数据已清除'}


# =========== 每日自动更新（跨天定时器） ===========
# 每天凌晨 05:30 之后执行一次：把 K线库所有已加载市场（stock_market 表记录）
# 逐个串行执行一次增量更新（update_market）。
# 实现方式：维护一个"下一次执行时刻" _auto_next_run，启动时初始化为明天 05:30
# （无论何时启动，当天都不触发）；轮询发现当前时间越过该时刻就执行一次更新，
# 并把下一次执行时刻推进到（执行当天）的次日 05:30，如此每天一次。

# 触发时刻（时, 分）。不选 0 点：美股收盘是北京时间 04:00(夏令时)/05:00(冬令时)，
# 0 点跑会拉入美股未完结的盘中 bar，且同日数据 INSERT OR IGNORE 无法再覆盖修正。
# 取 05:30 保证所有市场都已收盘、K线定稿。
_AUTO_UPDATE_TIME = (5, 30)
_AUTO_UPDATE_TICK = 60          # 触发检查间隔（秒）
_auto_next_run = None           # 下一次应执行更新库的时刻（datetime）


def _auto_update_all_markets():
    """遍历 K线库所有已加载市场，逐个串行执行增量更新"""
    markets = [m for m in market_all() if m in SEGMENTS]
    if not markets:
        print('[sync] 每日自动更新K线库: K线库暂无已加载市场，跳过')
        return
    total = len(markets)
    labels = ', '.join(SEGMENTS[m]['label'] for m in markets)
    print(f'[sync] 每日自动更新K线库: 开始，共 {total} 个市场 ({labels})')
    for idx, seg_key in enumerate(markets, 1):
        label = SEGMENTS[seg_key]['label']
        # 等待系统空闲再启动该市场，避免与手动加载/更新/清库操作冲突
        while _sync_status['running']:
            time.sleep(5)
        result = update_market(seg_key)
        if not result.get('success'):
            print(f'[sync] 每日自动更新K线库 [{idx}/{total}] {label}: 跳过 ({result.get("error")})')
            continue
        print(f'[sync] 每日自动更新K线库 [{idx}/{total}] {label}: 更新中...')
        while _sync_status['running']:
            time.sleep(5)
        print(f'[sync] 每日自动更新K线库 [{idx}/{total}] {label}: 完成')
    print('[sync] 每日自动更新K线库: 全部市场执行完毕')


def _next_run_time(base):
    """返回 base 下一天的 05:30（自动更新每次应执行的时刻）"""
    nxt = base + datetime.timedelta(days=1)
    return nxt.replace(
        hour=_AUTO_UPDATE_TIME[0], minute=_AUTO_UPDATE_TIME[1], second=0, microsecond=0)


def _auto_update_loop():
    """后台守护线程：当前时间越过下次执行时刻后，执行一次全市场 K线自动更新"""
    global _auto_next_run
    while True:
        time.sleep(_AUTO_UPDATE_TICK)
        try:
            now = datetime.datetime.now()
            if now < _auto_next_run:
                continue
            # 以当前时间（而非 _auto_next_run）为基准推次日 05:30：
            # 即使某次因故迟醒跨越了多个执行点，也只会补跑一次，不会连环补跑
            _auto_next_run = _next_run_time(now)
            _auto_update_all_markets()
        except Exception as _e:
            print(f'[sync] 每日自动更新K线库异常: {type(_e).__name__}: {_e}')


def start_daily_auto_update():
    """启动每日自动更新守护线程（由 app.py 启动时调用）。

    下一次执行时刻初始化为"明天 05:30"：无论何时启动，当天都不会触发，
    首次更新统一发生在次日凌晨 05:30 之后，此后每天一次。
    """
    global _auto_next_run
    _auto_next_run = _next_run_time(datetime.datetime.now())
    threading.Thread(target=_auto_update_loop, daemon=True, name='daily-kline-auto-update').start()
    print(f"[sync] 每日自动更新K线库已启动（下次执行: {_auto_next_run:%Y-%m-%d %H:%M}）")
