"""市场数据：指数行情、分时走势、资金流、恐慌/风险指数、融资融券"""
import datetime
import time
import threading
import requests
from concurrent.futures import ThreadPoolExecutor
from . import REQUEST_PROXIES

# ===== 共享 =====
_EM_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Referer': 'https://data.eastmoney.com/',
}
_EM_UT = 'bd1d9ddb04089700cf9c27f6f7426281'

# 简单内存缓存（5 秒 TTL，配合前端 10s 轮询可避免重复计算）
_cache = {}

def _cached(key, ttl=5):
    """如果 key 在 ttl 秒内已缓存则返回缓存值，否则返回 None"""
    if key in _cache:
        val, ts = _cache[key]
        if time.time() - ts < ttl:
            return val
    return None

def _cache_set(key, val):
    _cache[key] = (val, time.time())


# ===== 后台轮询：指数行情自动抓取 =====

_MAJOR_INDICES_KEY = 'major_indices'
_MARKET_BREADTH_KEY = 'market_breadth'
_SH_MINUTE_KEY = 'sh_minute'
_FUND_FLOW_KEY = 'fund_flow'
_TURNOVER_MINUTE_KEY = 'turnover_minute'
_MARGIN_KEY = 'margin_trading'
_DAILY_CLOSES_KEY = 'daily_closes'

def _is_trading_time():
    """判断当前是否在A股交易时段（周一至周五 09:15-11:35, 12:55-15:05）"""
    now = datetime.datetime.now()
    day = now.weekday()  # 0=周一, 6=周日
    if day >= 5:  # 周六日
        return False
    t = now.hour * 60 + now.minute
    return (555 <= t <= 695) or (775 <= t <= 905)
    # 09:15=555, 11:35=695, 12:55=775, 15:05=905


def _fetch_and_cache_major_indices():
    """抓取沪深指数行情并写入缓存（内部函数，复用了 get_major_indices 原始逻辑）"""
    try:
        url = "https://push2delay.eastmoney.com/api/qt/ulist.np/get"
        params = {
            'fltt': 2, 'invt': 2,
            'fields': 'f2,f3,f4,f12,f14',
            'secids': '1.000001,0.399001',
            'ut': _EM_UT,
        }
        r = requests.get(url, params=params, headers=_EM_HEADERS, timeout=8, proxies=REQUEST_PROXIES)
        diff = (r.json().get('data') or {}).get('diff') or []
        if diff:
            data = []
            for row in diff:
                code = row.get('f12', '')
                name = row.get('f14', '')
                price = row.get('f2')
                change_pct = row.get('f3')
                change_val = row.get('f4')
                data.append({
                    'code': code,
                    'name': name,
                    'price': f"{float(price):.2f}" if price else '-',
                    'change': f"{'+' if change_pct and float(change_pct) >= 0 else ''}{float(change_pct):.2f}%" if change_pct is not None else '0.00%',
                    'change_value': f"{'+' if change_val and float(change_val) >= 0 else ''}{float(change_val):.2f}" if change_val is not None else '+0.00',
                })
            if data:
                _cache[_MAJOR_INDICES_KEY] = ({'success': True, 'data': data}, time.time())
                return True
    except Exception as e:
        print(f"[major-indices poller] fetch error: {e}")
    return False


def _fetch_and_cache_breadth():
    """抓取沪深涨跌家数并写入缓存"""
    try:
        url = "https://push2delay.eastmoney.com/api/qt/ulist.np/get"
        params = {'fltt': 2, 'invt': 2, 'fields': 'f104,f105', 'secids': '1.000001,0.399001', 'ut': _EM_UT}
        r = requests.get(url, params=params, headers=_EM_HEADERS, timeout=8, proxies=REQUEST_PROXIES)
        diff = (r.json().get('data') or {}).get('diff') or []
        rise = sum(int(row.get('f104', 0)) for row in diff)
        fall = sum(int(row.get('f105', 0)) for row in diff)
        _cache[_MARKET_BREADTH_KEY] = ((rise, fall), time.time())
        return True
    except Exception as e:
        print(f"[breadth poller] fetch error: {e}")
    return False


def _fetch_and_cache_sh_minute():
    """抓取上证分时走势并写入缓存"""
    try:
        url = "https://push2delay.eastmoney.com/api/qt/stock/trends2/get?secid=1.000001&fields1=f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13&fields2=f51,f52,f53,f54,f55,f56,f57,f58&ndays=1"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36', 'Accept': '*/*', 'Referer': 'https://www.eastmoney.com/'}
        r = requests.get(url, headers=headers, timeout=10, proxies=REQUEST_PROXIES)
        data = r.json()
        if data.get('rc') == 0 and data.get('data'):
            sd = data['data']
            trends = sd.get('trends', [])
            pre_close = sd.get('preClose', 0)
            times, prices = [], []
            for trend in trends:
                parts = trend.split(',')
                if len(parts) >= 2:
                    time_str = parts[0].split(' ')[-1] if ' ' in parts[0] else parts[0]
                    if time_str < '09:30':
                        continue
                    times.append(time_str)
                    prices.append(float(parts[1]))
            cp = prices[-1] if prices else pre_close
            cv = cp - pre_close if pre_close else 0
            cpt = (cv / pre_close * 100) if pre_close else 0
            result = {
                'success': True,
                'data': {
                    'name': sd.get('name', '上证指数'),
                    'preClose': pre_close,
                    'currentPrice': cp,
                    'change': f"{'+' if cpt >= 0 else ''}{cpt:.2f}%",
                    'changeValue': f"{'+' if cv >= 0 else ''}{cv:.2f}",
                    'times': times, 'prices': prices,
                }
            }
            _cache[_SH_MINUTE_KEY] = (result, time.time())
            return True
    except Exception as e:
        print(f"[sh-minute poller] fetch error: {e}")
    return False


def _fetch_and_cache_fund_flow():
    """抓取大盘资金净流入分时并写入缓存（沪深两市合计）"""
    try:
        url = "https://push2delay.eastmoney.com/api/qt/stock/fflow/kline/get"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'Referer': 'https://data.eastmoney.com/', 'Accept': '*/*',
        }
        base_params = {
            'lmt': 0, 'klt': 1,
            'fields1': 'f1,f2,f3,f7', 'fields2': 'f51,f52,f53,f54,f55,f56,f57,f58',
            'ut': 'b2884a393a59ad64002292a3e90d46a5',
        }

        def _fetch(secid):
            p = dict(base_params)
            p['secid'] = secid
            r = requests.get(url, params=p, headers=headers, timeout=10, proxies=REQUEST_PROXIES)
            klines = (r.json().get('data') or {}).get('klines') or []
            result = {}
            for k in klines:
                parts = str(k).split(',')
                if len(parts) >= 2:
                    t = parts[0].split(' ')[-1][:5] if ' ' in parts[0] else parts[0]
                    result[t] = {
                        'flow': float(parts[1]) / 1e8,
                        'mid': float(parts[3]) / 1e8 if len(parts) > 3 else 0,
                        'small': float(parts[2]) / 1e8,
                    }
            return result

        sh_data = _fetch('1.000001')
        sz_data = _fetch('0.399001')

        all_times = sorted(set(list(sh_data.keys()) + list(sz_data.keys())))
        if not all_times:
            return False

        all_times = [t for t in all_times if t >= '09:30']
        flows, flows_mid, flows_small = [], [], []
        for t in all_times:
            sh = sh_data.get(t, {'flow': 0, 'mid': 0, 'small': 0})
            sz = sz_data.get(t, {'flow': 0, 'mid': 0, 'small': 0})
            flows.append(round(sh['flow'] + sz['flow'], 2))
            flows_mid.append(round(sh['mid'] + sz['mid'], 2))
            flows_small.append(round(sh['small'] + sz['small'], 2))

        if all_times and all_times[0] != '09:30':
            all_times.insert(0, '09:30')
            flows.insert(0, 0)
            flows_mid.insert(0, 0)
            flows_small.insert(0, 0)

        result = {
            'success': True,
            'data': {
                'date': datetime.date.today().strftime('%Y-%m-%d'),
                'times': all_times, 'flows': flows,
                'flows_mid': flows_mid, 'flows_small': flows_small
            }
        }
        _cache[_FUND_FLOW_KEY] = (result, time.time())
        return True
    except Exception as e:
        print(f"[fund-flow poller] fetch error: {e}")
    return False


def _fetch_and_cache_turnover():
    """抓取成交额分时数据并写入缓存"""
    try:
        url = "https://dq.10jqka.com.cn/fuyao/market_analysis_api/chart/v1/get_chart_data?chart_key=turnover_minute"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://www.10jqka.com.cn/',
            'Accept': 'application/json, text/plain, */*',
        }
        r = requests.get(url, headers=headers, timeout=10, proxies=REQUEST_PROXIES)
        data = r.json()
        if data.get('status_code') != 0:
            return False
        chart_data = data.get('data', {}).get('charts', {})
        header = chart_data.get('header', [])
        point_list = chart_data.get('point_list', [])
        if not point_list:
            return False

        day_groups = {}
        for point in point_list:
            if len(point) >= 3 and point[1] is not None and point[2] is not None:
                dt = datetime.datetime.fromtimestamp(point[0] // 1000)
                date_key = dt.strftime('%Y-%m-%d')
                day_groups.setdefault(date_key, []).append((dt, point[1] / 1e8, point[2] / 1e8))

        if not day_groups:
            return False
        latest_day = sorted(day_groups.keys())[-1]
        filtered_points = day_groups[latest_day]
        times, turnovers, predict_turnovers = [], [], []
        for dt, t, pt in filtered_points:
            times.append(dt.strftime('%H:%M'))
            turnovers.append(t)
            predict_turnovers.append(pt)

        header_info = {}
        for h in header:
            header_info[h['key']] = h['val']

        result = {
            'success': True,
            'data': {
                'times': times,
                'turnovers': turnovers,
                'predict_turnovers': predict_turnovers,
                'header': header_info
            }
        }
        _cache[_TURNOVER_MINUTE_KEY] = (result, time.time())
        return True
    except Exception as e:
        print(f"[turnover poller] fetch error: {e}")
    return False


def _fetch_and_cache_margin():
    """抓取融资融券沪深两市数据并写入缓存（供图表+风险指数共用）"""
    try:
        import akshare as ak
        end_date = datetime.date.today().strftime('%Y%m%d')
        start_date = (datetime.date.today() - datetime.timedelta(days=60)).strftime('%Y%m%d')

        def _get_df(func, *args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception:
                return None

        with ThreadPoolExecutor(max_workers=2) as pool:
            fut_sse = pool.submit(_get_df, ak.stock_margin_sse, start_date=start_date, end_date=end_date)
            fut_szse = pool.submit(_get_df, ak.stock_margin_szse, start_date=start_date, end_date=end_date)
            sse_df = fut_sse.result()
            szse_df = fut_szse.result()

        # 沪深两市按日期合并
        combined = {}
        for df in [sse_df, szse_df]:
            if df is not None and not df.empty:
                for _, row in df.iterrows():
                    d = str(row['信用交易日期'])
                    rz_val = float(row.get('融资余额', 0) or 0) / 1e8
                    rq_val = float(row.get('融券余量金额', 0) or 0) / 1e8
                    total_val = float(row.get('融资融券余额', 0) or 0) / 1e8
                    buy_val = float(row.get('融资买入额', 0) or 0) / 1e8
                    if d not in combined:
                        combined[d] = [rz_val, rq_val, total_val, buy_val]
                    else:
                        combined[d][0] += rz_val
                        combined[d][1] += rq_val
                        combined[d][2] += total_val
                        combined[d][3] += buy_val

        if not combined:
            return False

        # -- 图表数据 --
        sorted_dates = sorted(combined.keys())
        dates, rz_balances, rq_balances, total_balances, buy_amounts = [], [], [], [], []
        for d in sorted_dates:
            fmt_d = d[:4] + '-' + d[4:6] + '-' + d[6:8]
            dates.append(fmt_d[-5:])
            rz_balances.append(round(combined[d][0], 2))
            rq_balances.append(round(combined[d][1], 2))
            total_balances.append(round(combined[d][2], 2))
            buy_amounts.append(round(combined[d][3], 2))

        latest = combined[sorted_dates[-1]]

        # -- 风险指数融资因子 --
        fin_data = {}
        if len(sorted_dates) >= 2:
            latest_total = latest[2]
            latest_buy = latest[3]

            if len(sorted_dates) >= 6:
                t5_total = combined[sorted_dates[-6]][2]
                fin_data['fin_bal_5d'] = round((latest_total - t5_total) / t5_total * 100, 2) if t5_total else 0

            if len(sorted_dates) >= 11:
                t10_total = combined[sorted_dates[-11]][2]
                fin_data['fin_bal_10d'] = round((latest_total - t10_total) / t10_total * 100, 2) if t10_total else 0

            if len(sorted_dates) >= 21:
                recent_buys = [combined[d][3] for d in sorted_dates[-21:]]
                avg_20d = sum(recent_buys) / len(recent_buys) if recent_buys else 0
                fin_data['fin_buy_heat'] = round((latest_buy - avg_20d) / avg_20d * 100, 2) if avg_20d else 0

        result = {
            'success': True,
            'data': {
                'dates': dates, 'rz_balances': rz_balances, 'rq_balances': rq_balances,
                'total_balances': total_balances, 'buy_amounts': buy_amounts,
                'latest_date': dates[-1] if dates else '',
                'latest_rz': round(latest[0], 2),
                'latest_rq': round(latest[1], 2),
                'latest_total': round(latest[2], 2),
                'fin_bal_5d': fin_data.get('fin_bal_5d', 0.0),
                'fin_bal_10d': fin_data.get('fin_bal_10d', 0.0),
                'fin_buy_heat': fin_data.get('fin_buy_heat', 0.0),
            }
        }
        _cache[_MARGIN_KEY] = (result, datetime.date.today().strftime('%Y-%m-%d'))
        return True
    except Exception as e:
        print(f"[margin poller] fetch error: {e}")
    return False


def _fetch_and_cache_daily_closes():
    """抓取沪深指数30天日K收盘价并写入缓存（push2his 需走系统代理）"""
    import os as _os3
    _old_no = _os3.environ.pop('no_proxy', None)
    _old_NO = _os3.environ.pop('NO_PROXY', None)
    try:
        result = {}
        for symbol in ['sh000001', 'sz399001']:
            code = '0.' + symbol[2:] if symbol.startswith('sz') else '1.' + symbol[2:]
            today = datetime.date.today().strftime('%Y%m%d')
            ago = (datetime.date.today() - datetime.timedelta(days=30)).strftime('%Y%m%d')
            url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
            params = {
                'secid': code,
                'fields1': 'f1,f2,f3,f4,f5,f6',
                'fields2': 'f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61',
                'klt': 101, 'fqt': 0,
                'beg': ago, 'end': today,
                'ut': _EM_UT,
            }
            r = requests.get(url, params=params, headers=_EM_HEADERS, timeout=10)
            klines = (r.json().get('data') or {}).get('klines') or []
            closes = [float(k.split(',')[2]) for k in klines if len(k.split(',')) >= 3]
            result[symbol] = closes
        _cache[_DAILY_CLOSES_KEY] = (result, datetime.date.today().strftime('%Y-%m-%d'))
        return True
    except Exception as e:
        print(f"[daily-closes poller] fetch error: {e}")
    finally:
        if _old_no is not None: _os3.environ['no_proxy'] = _old_no
        if _old_NO is not None: _os3.environ['NO_PROXY'] = _old_NO
    return False


def _background_poller():
    """后台线程：启动时立即抓取，之后交易时段按不同频率自动抓取"""
    # 启动时立即抓取一次
    _fetch_and_cache_major_indices()
    _fetch_and_cache_breadth()
    _fetch_and_cache_sh_minute()
    _fetch_and_cache_fund_flow()
    _fetch_and_cache_turnover()
    _fetch_and_cache_margin()
    _fetch_and_cache_daily_closes()

    _loop_count = 0
    while True:
        time.sleep(5)
        _loop_count += 1
        try:
            if _is_trading_time():
                _fetch_and_cache_major_indices()   # 每 5s
                _fetch_and_cache_breadth()          # 每 5s
                if _loop_count % 12 == 0:           # 每 60s（12×5s）
                    _fetch_and_cache_sh_minute()
                    _fetch_and_cache_fund_flow()
                    _fetch_and_cache_turnover()
                    # 融资融券+日K：每天只抓一次（跨天后自动更新）
                    _today_str = datetime.date.today().strftime('%Y-%m-%d')
                    _cached_margin = _cache.get(_MARGIN_KEY)
                    if not _cached_margin or _cached_margin[1] != _today_str:
                        _fetch_and_cache_margin()
                    _cached_closes = _cache.get(_DAILY_CLOSES_KEY)
                    if not _cached_closes or _cached_closes[1] != _today_str:
                        _fetch_and_cache_daily_closes()
        except Exception:
            pass


def start_major_indices_poller():
    """启动指数行情后台轮询线程（由 app.py 调用）"""
    t = threading.Thread(target=_background_poller, daemon=True, name='major-indices-poller')
    t.start()


def get_major_indices():
    """上证指数实时行情（数据由后台轮询线程自动更新，此处仅读缓存）"""
    if _MAJOR_INDICES_KEY in _cache:
        return _cache[_MAJOR_INDICES_KEY][0]
    return {'success': False, 'error': '暂无指数数据'}


def get_sh000001_minute_data():
    """上证指数分时走势（数据由后台轮询线程每分钟更新，此处仅读缓存）"""
    cached = _cache.get(_SH_MINUTE_KEY)
    if cached:
        return cached[0]
    return {'success': False, 'error': '暂无分时数据'}


def get_market_fund_flow():
    """大盘资金净流入分时（优先读缓存，缓存空时同步抓取）"""
    cached = _cache.get(_FUND_FLOW_KEY)
    if cached:
        return cached[0]
    _fetch_and_cache_fund_flow()
    cached = _cache.get(_FUND_FLOW_KEY)
    if cached:
        return cached[0]
    return {'success': False, 'error': '暂无资金流数据'}


def get_fear_index():
    """市场恐慌指数：指数走势+日内分时+涨跌面+资金流 多因子加权 0-100"""
    cache_key = 'fear_index'
    cached = _cached(cache_key)
    if cached is not None:
        return cached

    try:
        # ---- 沪深涨跌幅：直接从大盘行情缓存读取（免去重复请求东财）----
        idx_changes = []
        major_cached = _cache.get(_MAJOR_INDICES_KEY)
        if major_cached and major_cached[0].get('success'):
            for item in major_cached[0]['data']:
                chg_str = item.get('change', '0%')
                try:
                    idx_changes.append(float(chg_str.replace('%', '')))
                except (ValueError, AttributeError):
                    idx_changes.append(0.0)

        # ---- 并行获取其余 4 个独立数据源 ----
        minute = None
        sz_intraday = 0.0
        rise = fall = 0
        fund = None

        with ThreadPoolExecutor(max_workers=4) as pool:
            # 1. 上证分时数据
            fut_min = pool.submit(get_sh000001_minute_data)
            # 2. 深证分时
            fut_sz = pool.submit(_fetch_sz_intraday)
            # 3. 涨跌家数 + 资金流
            fut_breadth = pool.submit(_fetch_breadth)
            fut_fund = pool.submit(get_market_fund_flow)

            minute = fut_min.result()
            sz_intraday = fut_sz.result()
            rise, fall = fut_breadth.result()
            fund = fut_fund.result()

        avg_idx_change = sum(idx_changes) / len(idx_changes) if idx_changes else 0

        # ---- 计算分时指标 ----
        intraday_pct_sh = 0.0
        intraday_pct = 0.0
        max_30m_drop = 0.0
        max_dd = 0.0
        amplitude = 0.0
        rebound = 0.0

        if minute.get('success') and minute.get('data'):
            md = minute['data']
            prices = [p for p in md.get('prices', []) if p is not None]
            pre_close = md.get('preClose', 0)
            if prices and pre_close:
                cur = prices[-1]
                intraday_pct_sh = round((cur - pre_close) / pre_close * 100, 2)
                hi = max(prices)
                lo = min(prices)
                amplitude = round((hi - lo) / pre_close * 100, 2)
                peak = prices[0]
                for p in prices:
                    if p > peak: peak = p
                    dd = (p - peak) / peak * 100
                    if dd < max_dd: max_dd = dd
                max_dd = round(max_dd, 2)
                for i in range(len(prices) - 30):
                    if prices[i] > 0:
                        drop = (prices[i + 30] - prices[i]) / prices[i] * 100
                        if drop < max_30m_drop: max_30m_drop = drop
                max_30m_drop = round(max_30m_drop, 2)
                if lo:
                    rebound = round((cur - lo) / lo * 100, 2)

        intraday_pct = round((intraday_pct_sh + sz_intraday) / 2, 2) if sz_intraday else intraday_pct_sh

        # ---- 广度数据 ----
        total_active = rise + fall
        red_ratio = round(rise / total_active * 100, 1) if total_active > 0 else 50
        down_ratio = round(fall / total_active * 100, 1) if total_active > 0 else 50

        # ---- 资金 ----
        main_net = 0.0
        if fund.get('success') and fund.get('data'):
            flows = fund['data'].get('flows', [])
            main_net = round(flows[-1], 2) if flows else 0

        # === 加权合成 ===
        index_pressure = min(max(abs(avg_idx_change) * 8, 0), 22)
        intraday_pressure = 0.0
        intraday_pressure += min(max(abs(intraday_pct) * 6, 0), 8)
        intraday_pressure += min(max(abs(max_30m_drop) * 12, 0), 8)
        intraday_pressure += min(max(abs(max_dd) * 8, 0), 6)
        intraday_pressure += min(max(amplitude * 1.5, 0), 2)
        intraday_pressure = round(min(intraday_pressure, 28), 1)
        breadth_pressure = 0.0
        breadth_pressure += min(max((50 - red_ratio) * 0.3, 0), 12)
        breadth_pressure += min(max((down_ratio - 50) * 0.25, 0), 8)
        breadth_pressure = round(min(breadth_pressure, 22), 1)
        fund_pressure = round(min(max(abs(main_net) / 100 * 0.7, 0), 12), 1) if main_net < 0 else 0
        stabilization = round(min(max(rebound * 2.5, 0), 6), 1)

        base = 20
        score = round(base + index_pressure + intraday_pressure + breadth_pressure + fund_pressure - stabilization, 1)
        score = max(0, min(100, score))

        if score <= 30:
            level, color = '平稳', '#4ade80'
        elif score <= 50:
            level, color = '轻度恐慌', '#86efac'
        elif score <= 65:
            level, color = '明显恐慌', '#fbbf24'
        elif score <= 80:
            level, color = '高度恐慌', '#f97316'
        else:
            level, color = '极度恐慌', '#e94560'

        result = {
            'success': True,
            'data': {
                'score': score, 'level': level, 'color': color,
                'rise': rise, 'fall': fall, 'flat': 0,
                'avg_index_change': round(avg_idx_change, 2),
                'intraday_pct': intraday_pct,
                'max_30m_drop': max_30m_drop,
                'max_drawdown': max_dd,
                'amplitude': amplitude,
                'red_ratio': red_ratio,
                'down_ratio': down_ratio,
                'main_net': main_net,
                'rebound': round(rebound, 2),
            }
        }
        _cache_set(cache_key, result)
        return result
    except Exception as e:
        return {'success': False, 'error': str(e)}


# ---- 内部辅助函数 ----

def _fetch_idx_changes():
    """东财获取沪深指数涨跌幅"""
    changes = []
    try:
        url = "https://push2delay.eastmoney.com/api/qt/ulist.np/get"
        params = {'fltt': 2, 'invt': 2, 'fields': 'f3', 'secids': '1.000001,0.399001', 'ut': _EM_UT}
        r = requests.get(url, params=params, headers=_EM_HEADERS, timeout=8, proxies=REQUEST_PROXIES)
        for row in (r.json().get('data') or {}).get('diff') or []:
            try:
                changes.append(float(row.get('f3', 0)))
            except Exception:
                pass
    except Exception:
        pass
    return changes


def _fetch_sz_intraday():
    """获取深证成指日内涨跌（从大盘行情缓存读取）"""
    major_cached = _cache.get(_MAJOR_INDICES_KEY)
    if major_cached and major_cached[0].get('success') and len(major_cached[0]['data']) > 1:
        chg_str = major_cached[0]['data'][1].get('change', '0%')
        try:
            return float(chg_str.replace('%', ''))
        except (ValueError, AttributeError):
            pass
    return 0.0


def _fetch_breadth():
    """获取沪深涨跌家数（从后台缓存读取，不发起网络请求）"""
    cached = _cache.get(_MARKET_BREADTH_KEY)
    if cached:
        return cached[0]  # (rise, fall)
    return 0, 0


def get_risk_index():
    """市场风险指数：融资杠杆+指数趋势+情绪面+涨跌结构 多因子加权 0-100"""
    cache_key = 'risk_index'
    cached = _cached(cache_key)
    if cached is not None:
        return cached

    try:
        # ---- 并行获取 4 个独立数据源 ----
        margin_data = {}
        closes_sh = []
        closes_sz = []
        rise = fall = 0

        with ThreadPoolExecutor(max_workers=4) as pool:
            fut_margin = pool.submit(_fetch_margin)
            fut_sh = pool.submit(_fetch_daily_closes, 'sh000001')
            fut_sz = pool.submit(_fetch_daily_closes, 'sz399001')
            fut_breadth = pool.submit(_fetch_breadth)

            margin_data = fut_margin.result()
            closes_sh = fut_sh.result()
            closes_sz = fut_sz.result()
            rise, fall = fut_breadth.result()

        # === 1. 融资因子 (0-35) ===
        financing_score = 0.0
        fin_bal_5d = margin_data.get('fin_bal_5d', 0.0)
        fin_bal_10d = margin_data.get('fin_bal_10d', 0.0)
        fin_buy_heat = margin_data.get('fin_buy_heat', 0.0)

        financing_score += min(max(fin_bal_10d * 3, 0), 18)
        financing_score += min(max(fin_bal_5d * 4, 0), 12)
        if fin_buy_heat < 0:
            financing_score += min(max(abs(fin_buy_heat) * 0.5, 0), 5)
        financing_score = round(min(financing_score, 35), 1)

        # === 2. 指数趋势因子 (0-30) ===
        trend_score, vol, idx_5d, idx_10d, idx_20d_dd = _calc_trend(closes_sh, closes_sz)

        # === 3. 情绪面因子 (0-20) — 直接算，不嵌套 get_fear_index ===
        sentiment_score = 0.0
        try:
            red_ratio = round(rise / (rise + fall) * 100, 1) if (rise + fall) > 0 else 50
            # 用涨跌面粗略估算市场情绪压力
            sentiment_score += min(max((50 - red_ratio) * 0.3, 0), 12)
            # 涨跌差作为辅助
            if (rise + fall) > 0:
                diff_ratio = abs(rise - fall) / (rise + fall) * 100
                sentiment_score += min(max(diff_ratio * 0.08, 0), 8)
        except Exception:
            pass
        sentiment_score = round(min(sentiment_score, 20), 1)

        # === 4. 涨跌结构因子 (0-15) ===
        limit_score = 0.0
        total = rise + fall
        if total > 0:
            limit_score += min(max(abs(rise - fall) / total * 10, 0), 8)
            limit_score += min(max(fall / total * 15, 0), 7)
        limit_score = round(min(limit_score, 15), 1)

        score = round(financing_score + trend_score + sentiment_score + limit_score, 1)
        score = max(0, min(100, score))

        if score <= 20:
            level, color = '低风险', '#4ade80'
        elif score <= 40:
            level, color = '较低风险', '#86efac'
        elif score <= 60:
            level, color = '中等风险', '#fbbf24'
        elif score <= 80:
            level, color = '较高风险', '#f97316'
        else:
            level, color = '高风险', '#e94560'

        result = {
            'success': True,
            'data': {
                'score': score, 'level': level, 'color': color,
                'volatility': round(vol, 2),
                'leverage': round(fin_bal_10d, 2),
                'fin_bal_5d': fin_bal_5d,
                'fin_bal_10d': fin_bal_10d,
                'fin_buy_heat': fin_buy_heat,
                'idx_5d': idx_5d,
                'idx_10d': idx_10d,
                'idx_20d_dd': idx_20d_dd,
                'panic_score_in': round(sentiment_score, 1),
                'limit_score_in': round(limit_score, 1),
            }
        }
        _cache_set(cache_key, result)
        return result
    except Exception as e:
        return {'success': False, 'error': str(e)}


# ---- 风险指数辅助函数 ----

def _fetch_margin():
    """获取融资因子数据（从后台融资融券缓存读取，不发起网络请求）"""
    cached = _cache.get(_MARGIN_KEY)
    if cached and cached[0].get('success'):
        d = cached[0]['data']
        return {
            'fin_bal_5d': d.get('fin_bal_5d', 0.0),
            'fin_bal_10d': d.get('fin_bal_10d', 0.0),
            'fin_buy_heat': d.get('fin_buy_heat', 0.0),
        }
    return {}


def _fetch_daily_closes(symbol):
    """获取日线收盘价（从后台缓存读取，不发起网络请求）"""
    cached = _cache.get(_DAILY_CLOSES_KEY)
    if cached:
        return cached[0].get(symbol, [])
    return []


def _calc_trend(sh_c, sz_c):
    """计算趋势指标：5日涨跌、10日涨跌、20日最大回撤、波动率"""
    trend_score = 0.0
    vol = 0.0
    idx_5d = 0.0
    idx_10d = 0.0
    idx_20d_dd = 0.0

    try:
        n = min(len(sh_c), len(sz_c)) if sh_c and sz_c else len(sh_c or sz_c or [])
        if n >= 5:
            avg_closes = [(sh_c[i] + sz_c[i]) / 2 for i in range(n)] if sh_c and sz_c else (sh_c or sz_c)
            cur_close = avg_closes[-1]

            if len(avg_closes) >= 6:
                idx_5d = round((cur_close - avg_closes[-6]) / avg_closes[-6] * 100, 2)
            if len(avg_closes) >= 11:
                idx_10d = round((cur_close - avg_closes[-11]) / avg_closes[-11] * 100, 2)

            if len(avg_closes) >= 21:
                recent = avg_closes[-21:]
                peak = recent[0]
                max_dd_20d = 0.0
                for c in recent:
                    if c > peak: peak = c
                    dd = (c - peak) / peak * 100
                    if dd < max_dd_20d: max_dd_20d = dd
                idx_20d_dd = round(max_dd_20d, 2)

            if len(avg_closes) >= 11:
                recent10 = avg_closes[-11:]
                changes = [(recent10[i] - recent10[i-1]) / recent10[i-1] * 100 for i in range(1, len(recent10))]
                avg_ch = sum(changes) / len(changes)
                variance = sum((c - avg_ch) ** 2 for c in changes) / len(changes)
                vol = round(variance ** 0.5, 2)
    except Exception:
        pass

    trend_score += min(max(abs(idx_5d) * 3, 0), 10)
    trend_score += min(max(abs(idx_10d) * 2, 0), 8)
    trend_score += min(max(abs(idx_20d_dd) * 2, 0), 7)
    trend_score += min(max(vol * 3, 0), 5)
    trend_score = round(min(trend_score, 30), 1)

    return trend_score, vol, idx_5d, idx_10d, idx_20d_dd


def get_margin_trading():
    """融资融券：沪市每日数据（数据由后台轮询线程每日更新，此处仅读缓存）"""
    cached = _cache.get(_MARGIN_KEY)
    if cached:
        return cached[0]
    return {'success': False, 'error': '暂无融资融券数据'}
