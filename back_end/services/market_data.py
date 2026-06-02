"""市场数据：指数行情、分时走势、资金流、恐慌/风险指数、融资融券"""
import datetime
import time
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


def get_major_indices():
    """上证指数实时行情"""
    cache_key = 'major_indices'
    cached = _cached(cache_key, ttl=3)
    if cached is not None:
        return cached
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
                result = {'success': True, 'data': data}
                _cache_set(cache_key, result)
                return result
    except Exception:
        pass
    return {'success': False, 'error': '东财指数行情请求失败'}


def get_sh000001_minute_data():
    """上证指数分时走势"""
    cache_key = 'sh_minute'
    cached = _cached(cache_key, ttl=5)
    if cached is not None:
        return cached
    try:
        url = "https://push2delay.eastmoney.com/api/qt/stock/trends2/get?secid=1.000001&fields1=f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13&fields2=f51,f52,f53,f54,f55,f56,f57,f58&ndays=1"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36', 'Accept': '*/*', 'Referer': 'https://www.eastmoney.com/'}
        response = requests.get(url, headers=headers, timeout=10, proxies=REQUEST_PROXIES)
        data = response.json()
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
            _cache_set(cache_key, result)
            return result
    except Exception:
        pass
    return {'success': False, 'error': '获取分时数据失败'}


def get_market_fund_flow():
    """大盘资金净流入分时（东财push2delay，沪深两市合计）"""
    cache_key = 'fund_flow'
    cached = _cached(cache_key, ttl=5)
    if cached is not None:
        return cached
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

        # 合并两个市场：收集所有时间点
        all_times = sorted(set(list(sh_data.keys()) + list(sz_data.keys())))
        if not all_times:
            return {'success': False, 'error': 'No fund flow data'}

        # 过滤盘前数据
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
        _cache_set(cache_key, result)
        return result
    except Exception as e:
        return {'success': False, 'error': str(e)}


def get_fear_index():
    """市场恐慌指数：指数走势+日内分时+涨跌面+资金流 多因子加权 0-100"""
    cache_key = 'fear_index'
    cached = _cached(cache_key)
    if cached is not None:
        return cached

    try:
        # ---- 并行获取 3 个独立数据源 ----
        idx_changes = []
        minute = None
        sz_intraday = 0.0
        rise = fall = 0
        fund = None

        with ThreadPoolExecutor(max_workers=4) as pool:
            # 1. 沪深指数变化（东财）
            fut_idx = pool.submit(_fetch_idx_changes)
            # 2. 上证分时数据
            fut_min = pool.submit(get_sh000001_minute_data)
            # 3. 深证分时
            fut_sz = pool.submit(_fetch_sz_intraday)
            # 4. 涨跌家数 + 资金流（可串行，资金流依赖强）
            fut_breadth = pool.submit(_fetch_breadth)
            fut_fund = pool.submit(get_market_fund_flow)

            idx_changes = fut_idx.result()
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
    """东财获取深证成指日内涨跌"""
    try:
        url = "https://push2delay.eastmoney.com/api/qt/stock/trends2/get?secid=0.399001&fields1=f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13&fields2=f51,f52,f53,f54,f55,f56,f57,f58&ndays=1"
        r = requests.get(url, headers=_EM_HEADERS, timeout=8, proxies=REQUEST_PROXIES)
        data = r.json()
        if data.get('rc') == 0:
            sd = data['data']
            prices = [float(t.split(',')[1]) for t in sd.get('trends', []) if len(t.split(',')) >= 2 and t.split(',')[0].split(' ')[-1] >= '09:30']
            pre = sd.get('preClose', 0)
            if prices and pre:
                return round((prices[-1] - pre) / pre * 100, 2)
    except Exception:
        pass
    return 0.0


def _fetch_breadth():
    """东财获取沪深涨跌家数"""
    try:
        url = "https://push2delay.eastmoney.com/api/qt/ulist.np/get"
        params = {'fltt': 2, 'invt': 2, 'fields': 'f104,f105,f106', 'secids': '1.000001,0.399001', 'ut': _EM_UT}
        r = requests.get(url, params=params, headers=_EM_HEADERS, timeout=8, proxies=REQUEST_PROXIES)
        diff = (r.json().get('data') or {}).get('diff') or []
        rise = sum(int(row.get('f104', 0)) for row in diff)
        fall = sum(int(row.get('f105', 0)) for row in diff)
        return rise, fall
    except Exception:
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
    """获取融资融券数据（akshare 爬虫，并行调用沪深两市）"""
    result = {}
    try:
        import akshare as ak
        end_date = datetime.date.today().strftime('%Y%m%d')
        start_date = (datetime.date.today() - datetime.timedelta(days=30)).strftime('%Y%m%d')

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

        combined = {}
        for df in [sse_df, szse_df]:
            if df is not None and not df.empty:
                for _, row in df.iterrows():
                    d = str(row['信用交易日期'])
                    rz_val = float(row.get('融资余额', 0) or 0)
                    rq_val = float(row.get('融券余量金额', 0) or 0)
                    buy_val = float(row.get('融资买入额', 0) or 0)
                    if d not in combined:
                        combined[d] = [rz_val, rq_val, buy_val]
                    else:
                        combined[d][0] += rz_val
                        combined[d][1] += rq_val
                        combined[d][2] += buy_val

        dates = sorted(combined.keys())
        if len(dates) >= 2:
            latest = combined[dates[-1]]
            latest_total = latest[0] + latest[1]
            latest_buy = latest[2]

            if len(dates) >= 6:
                t5 = combined[dates[-6]]
                total_5d = t5[0] + t5[1]
                result['fin_bal_5d'] = round((latest_total - total_5d) / total_5d * 100, 2) if total_5d else 0

            if len(dates) >= 11:
                t10 = combined[dates[-11]]
                total_10d = t10[0] + t10[1]
                result['fin_bal_10d'] = round((latest_total - total_10d) / total_10d * 100, 2) if total_10d else 0

            if len(dates) >= 21:
                recent_buys = [combined[d][2] for d in dates[-21:]]
                avg_20d = sum(recent_buys) / len(recent_buys) if recent_buys else 0
                result['fin_buy_heat'] = round((latest_buy - avg_20d) / avg_20d * 100, 2) if avg_20d else 0
    except Exception:
        pass
    return result


def _fetch_daily_closes(symbol):
    """东财获取日线收盘价"""
    try:
        code = '1.' + symbol[2:]  # sh000001 → 1.000001, sz399001 → 0.399001
        if symbol.startswith('sz'):
            code = '0.' + symbol[2:]
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
        r = requests.get(url, params=params, headers=_EM_HEADERS, timeout=8, proxies=REQUEST_PROXIES)
        klines = (r.json().get('data') or {}).get('klines') or []
        return [float(k.split(',')[2]) for k in klines if len(k.split(',')) >= 3]
    except Exception:
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
    """融资融券：沪市每日数据"""
    try:
        import akshare as ak
        end = datetime.date.today().strftime('%Y%m%d')
        start = (datetime.date.today() - datetime.timedelta(days=60)).strftime('%Y%m%d')
        df = ak.stock_margin_sse(start_date=start, end_date=end)
        if df is None or df.empty:
            return {'success': False, 'error': 'No data'}

        dates, rz, rq, total, buys = [], [], [], [], []
        for _, row in df.iterrows():
            d = str(row['信用交易日期'])
            d = d[:4] + '-' + d[4:6] + '-' + d[6:8]
            dates.insert(0, d[-5:])
            rz.insert(0, round(float(row['融资余额']) / 1e8, 2))
            rq.insert(0, round(float(row['融券余量金额']) / 1e8, 2))
            total.insert(0, round(float(row['融资融券余额']) / 1e8, 2))
            buys.insert(0, round(float(row['融资买入额']) / 1e8, 2))

        latest = df.iloc[0]
        return {
            'success': True,
            'data': {
                'dates': dates, 'rz_balances': rz, 'rq_balances': rq, 'total_balances': total, 'buy_amounts': buys,
                'latest_date': dates[-1] if dates else '',
                'latest_rz': round(float(latest['融资余额']) / 1e8, 2),
                'latest_rq': round(float(latest['融券余量金额']) / 1e8, 2),
                'latest_total': round(float(latest['融资融券余额']) / 1e8, 2),
            }
        }
    except Exception as e:
        return {'success': False, 'error': str(e)}
