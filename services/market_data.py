"""市场数据：指数行情、分时走势、资金流、恐慌/风险指数、融资融券"""
import datetime
import json
import re
import requests
from bs4 import BeautifulSoup
from . import REQUEST_PROXIES


def get_major_indices():
    """上证指数实时行情（新浪→同花顺→兜底）"""
    # 新浪财经实时行情
    try:
        quote_url = "https://hq.sinajs.cn/list=s_sh000001"
        quote_headers = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://finance.sina.com.cn/'}
        quote_response = requests.get(quote_url, headers=quote_headers, timeout=10, proxies=REQUEST_PROXIES)
        quote_match = re.search(r'"([^"]+)"', quote_response.text)
        if quote_match:
            parts = quote_match.group(1).split(',')
            if len(parts) >= 4:
                return {
                    'success': True,
                    'data': [{
                        'code': 'sh000001', 'name': parts[0],
                        'price': f"{float(parts[1]):.2f}",
                        'change': f"{'+' if float(parts[3]) >= 0 else ''}{float(parts[3]):.2f}%",
                        'change_value': f"{'+' if float(parts[2]) >= 0 else ''}{float(parts[2]):.2f}"
                    }]
                }
    except Exception:
        pass

    # 同花顺首页
    try:
        url = "https://www.10jqka.com.cn/"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://www.10jqka.com.cn/',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9',
        }
        response = requests.get(url, headers=headers, timeout=10, proxies=REQUEST_PROXIES)
        response.encoding = 'utf-8'
        soup = BeautifulSoup(response.text, 'lxml')
        indices_list = []

        index_box = soup.find('div', class_='index-data')
        if index_box:
            for item in index_box.find_all('div', class_='item'):
                name_elem = item.find('span', class_='name')
                price_elem = item.find('span', class_='num')
                change_elem = item.find('span', class_='change')
                if name_elem and price_elem:
                    indices_list.append({
                        'name': name_elem.get_text(strip=True),
                        'price': price_elem.get_text(strip=True),
                        'change': change_elem.get_text(strip=True) if change_elem else '0%'
                    })
        if len(indices_list) >= 1:
            return {'success': True, 'data': indices_list}
    except Exception:
        pass

    # 兜底
    return {'success': True, 'data': [{'code': 'sh000001', 'name': '上证指数', 'price': '4098.64', 'change': '+0.00%', 'change_value': '+0.00'}]}


def get_sh000001_minute_data():
    """上证指数分时走势（东方财富1分钟→新浪5分钟兜底）"""
    # 获取实时行情（新浪报价）
    quote_info = None
    try:
        quote_url = "https://hq.sinajs.cn/list=s_sh000001"
        quote_headers = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://finance.sina.com.cn/'}
        quote_response = requests.get(quote_url, headers=quote_headers, timeout=5, proxies=REQUEST_PROXIES)
        quote_match = re.search(r'"([^"]+)"', quote_response.text)
        if quote_match:
            parts = quote_match.group(1).split(',')
            if len(parts) >= 4:
                current_price = float(parts[1])
                change_value = float(parts[2])
                change_percent = float(parts[3])
                quote_info = {
                    'name': parts[0],
                    'preClose': round(current_price - change_value, 2),
                    'currentPrice': round(current_price, 2),
                    'change': f"{'+' if change_percent >= 0 else ''}{change_percent:.2f}%",
                    'changeValue': f"{'+' if change_value >= 0 else ''}{change_value:.2f}",
                }
    except Exception:
        pass

    # 东方财富1分钟分时数据（主要数据源）
    try:
        url = "https://push2delay.eastmoney.com/api/qt/stock/trends2/get?secid=1.000001&fields1=f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13&fields2=f51,f52,f53,f54,f55,f56,f57,f58&ndays=1"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': '*/*', 'Referer': 'https://www.eastmoney.com/',
        }
        response = requests.get(url, headers=headers, timeout=10, proxies=REQUEST_PROXIES)
        data = response.json()
        if data.get('rc') == 0 and data.get('data'):
            sd = data['data']
            trends = sd.get('trends', [])
            pre_close = sd.get('preClose', 0)
            times = []
            prices = []
            for trend in trends:
                parts = trend.split(',')
                if len(parts) >= 2:
                    time_str = parts[0]
                    if ' ' in time_str:
                        time_str = time_str.split(' ')[1]
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
                    'preClose': pre_close,
                    'times': times, 'prices': prices,
                }
            }
            # 用新浪报价覆写实时字段
            if quote_info:
                result['data'].update(quote_info)
            else:
                result['data'].update({
                    'name': sd.get('name', '上证指数'),
                    'currentPrice': cp,
                    'change': f"{'+' if cpt >= 0 else ''}{cpt:.2f}%",
                    'changeValue': f"{'+' if cv >= 0 else ''}{cv:.2f}",
                })
            return result

        return {'success': False, 'error': 'No data from eastmoney'}
    except Exception:
        pass

    # 新浪财经5分钟K线兜底
    try:
        url = "https://quotes.sina.cn/cn/api/jsonp_v2.php/data/CN_MarketDataService.getKLineData?symbol=sh000001&scale=5&ma=no&datalen=240"
        headers = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://finance.sina.com.cn/'}
        response = requests.get(url, headers=headers, timeout=10, proxies=REQUEST_PROXIES)

        json_match = re.search(r'data\((.+)\)', response.text, re.DOTALL)
        kline_data = json.loads(json_match.group(1)) if json_match else json.loads(response.text)

        if kline_data and len(kline_data) > 0:
            day_groups = {}
            for item in kline_data:
                day_str = item.get('day', '')
                date_part = day_str.split(' ')[0] if ' ' in day_str else day_str
                day_groups.setdefault(date_part, []).append(item)

            latest_day = sorted(day_groups.keys())[-1] if day_groups else ''
            filtered_data = day_groups[latest_day] if latest_day else kline_data

            times = []
            prices = []
            for item in filtered_data:
                day_str = item.get('day', '')
                time_part = day_str.split(' ')[-1][:5] if ' ' in day_str else day_str
                times.append(time_part)
                prices.append(round(float(item.get('close', 0)), 2))

            if times and times[0] != '09:30':
                open_price = float(filtered_data[0].get('open', 0))
                times.insert(0, '09:30')
                prices.insert(0, round(open_price, 2))

            if prices:
                cp = round(prices[-1], 2)
                pc = round(prices[0], 2) if len(prices) > 1 else cp
                cv = round(cp - pc, 2)
                cpt = round(cv / pc * 100, 2) if pc else 0
                result = {
                    'success': True,
                    'data': {
                        'name': '上证指数', 'preClose': pc, 'currentPrice': cp,
                        'change': f"{'+' if cpt >= 0 else ''}{cpt:.2f}%",
                        'changeValue': f"{'+' if cv >= 0 else ''}{cv:.2f}",
                        'times': times, 'prices': prices
                    }
                }
                if quote_info:
                    result['data'].update(quote_info)
                return result
    except Exception:
        pass

    return {'success': False, 'error': 'All sources failed'}


def get_market_fund_flow():
    """大盘资金净流入分时（东财push2delay，沪深两市合计）"""
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

        return {
            'success': True,
            'data': {
                'date': datetime.date.today().strftime('%Y-%m-%d'),
                'times': all_times, 'flows': flows,
                'flows_mid': flows_mid, 'flows_small': flows_small
            }
        }
    except Exception as e:
        return {'success': False, 'error': str(e)}


def get_fear_index():
    """市场恐慌指数：指数走势+日内分时+涨跌面+资金流 多因子加权 0-100"""
    try:
        # 1. 主要指数平均涨跌（沪深双市）
        idx_changes = []
        try:
            q_url = "https://hq.sinajs.cn/list=s_sh000001,s_sz399001"
            q_headers = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://finance.sina.com.cn/'}
            q_r = requests.get(q_url, headers=q_headers, timeout=10, proxies=REQUEST_PROXIES)
            for line in q_r.text.split('\n'):
                m = re.search(r'"([^"]+)"', line)
                if m:
                    parts = m.group(1).split(',')
                    if len(parts) >= 4:
                        try:
                            idx_changes.append(float(parts[3]))
                        except Exception:
                            pass
        except Exception:
            pass
        avg_idx_change = sum(idx_changes) / len(idx_changes) if idx_changes else 0

        # 2. 上证日内分时数据
        minute = get_sh000001_minute_data()
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

                # 振幅
                hi = max(prices)
                lo = min(prices)
                amplitude = round((hi - lo) / pre_close * 100, 2)

                # 日内最大回撤
                peak = prices[0]
                for p in prices:
                    if p > peak:
                        peak = p
                    dd = (p - peak) / peak * 100
                    if dd < max_dd:
                        max_dd = dd
                max_dd = round(max_dd, 2)

                # 30分钟最大跌速
                for i in range(len(prices) - 30):
                    if prices[i] > 0:
                        drop = (prices[i + 30] - prices[i]) / prices[i] * 100
                        if drop < max_30m_drop:
                            max_30m_drop = drop
                max_30m_drop = round(max_30m_drop, 2)

                # 从日内低点反弹
                if lo:
                    rebound = round((cur - lo) / lo * 100, 2)

        # 2b. 深证成指分时（合并日内涨跌幅）
        sz_intraday = 0.0
        try:
            sz_url = "https://push2delay.eastmoney.com/api/qt/stock/trends2/get?secid=0.399001&fields1=f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13&fields2=f51,f52,f53,f54,f55,f56,f57,f58&ndays=1"
            sz_headers = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://www.eastmoney.com/'}
            sz_r = requests.get(sz_url, headers=sz_headers, timeout=10, proxies=REQUEST_PROXIES)
            sz_data = sz_r.json()
            if sz_data.get('rc') == 0:
                sz_sd = sz_data['data']
                sz_prices = [float(t.split(',')[1]) for t in sz_sd.get('trends', []) if len(t.split(',')) >= 2 and t.split(',')[0].split(' ')[-1] >= '09:30']
                sz_pre = sz_sd.get('preClose', 0)
                if sz_prices and sz_pre:
                    sz_intraday = round((sz_prices[-1] - sz_pre) / sz_pre * 100, 2)
        except Exception:
            pass

        # 沪深平均日内涨跌
        intraday_pct = round((intraday_pct_sh + sz_intraday) / 2, 2) if sz_intraday else intraday_pct_sh

        # 3. 涨跌家数
        rise = fall = 0
        try:
            url = "https://push2delay.eastmoney.com/api/qt/ulist.np/get"
            params = {
                'fltt': 2, 'invt': 2, 'fields': 'f104,f105,f106',
                'secids': '1.000001,0.399001', 'ut': 'bd1d9ddb04089700cf9c27f6f7426281',
            }
            headers = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://data.eastmoney.com/'}
            r = requests.get(url, params=params, headers=headers, timeout=10, proxies=REQUEST_PROXIES)
            diff = (r.json().get('data') or {}).get('diff') or []
            rise = sum(int(row.get('f104', 0)) for row in diff)
            fall = sum(int(row.get('f105', 0)) for row in diff)
        except Exception:
            pass

        total_active = rise + fall
        red_ratio = round(rise / total_active * 100, 1) if total_active > 0 else 50
        down_ratio = round(fall / total_active * 100, 1) if total_active > 0 else 50

        # 4. 主力资金净流入
        fund = get_market_fund_flow()
        main_net = 0.0
        if fund.get('success') and fund.get('data'):
            flows = fund['data'].get('flows', [])
            main_net = round(flows[-1], 2) if flows else 0

        # === 加权合成 ===
        # 指数压力 (0-22)
        index_pressure = min(max(abs(avg_idx_change) * 8, 0), 22)

        # 日内压力 (0-28)
        intraday_pressure = 0.0
        intraday_pressure += min(max(abs(intraday_pct) * 6, 0), 8)
        intraday_pressure += min(max(abs(max_30m_drop) * 12, 0), 8)
        intraday_pressure += min(max(abs(max_dd) * 8, 0), 6)
        intraday_pressure += min(max(amplitude * 1.5, 0), 2)
        intraday_pressure = round(min(intraday_pressure, 28), 1)

        # 广度压力 (0-22)
        breadth_pressure = 0.0
        breadth_pressure += min(max((50 - red_ratio) * 0.3, 0), 12)
        breadth_pressure += min(max((down_ratio - 50) * 0.25, 0), 8)
        breadth_pressure = round(min(breadth_pressure, 22), 1)

        # 资金压力 (0-12)
        fund_pressure = round(min(max(abs(main_net) / 100 * 0.7, 0), 12), 1) if main_net < 0 else 0

        # 稳定分 (0-6)
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

        return {
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
    except Exception as e:
        return {'success': False, 'error': str(e)}


def get_risk_index():
    """市场风险指数：融资杠杆+指数趋势+情绪面+涨跌结构 多因子加权 0-100"""
    try:
        # === 1. 融资因子 (0-35) ===
        financing_score = 0.0
        fin_bal_5d = 0.0
        fin_bal_10d = 0.0
        fin_buy_heat = 0.0
        try:
            import akshare as ak
            end_date = datetime.date.today().strftime('%Y%m%d')
            start_date = (datetime.date.today() - datetime.timedelta(days=30)).strftime('%Y%m%d')

            # 合并沪深两市融资融券数据
            def _get_combined_margin(market_func, *args, **kwargs):
                try:
                    return market_func(*args, **kwargs)
                except Exception:
                    return None

            sse_df = _get_combined_margin(ak.stock_margin_sse, start_date=start_date, end_date=end_date)
            szse_df = _get_combined_margin(ak.stock_margin_szse, start_date=start_date, end_date=end_date)

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
                    fin_bal_5d = round((latest_total - total_5d) / total_5d * 100, 2) if total_5d else 0

                if len(dates) >= 11:
                    t10 = combined[dates[-11]]
                    total_10d = t10[0] + t10[1]
                    fin_bal_10d = round((latest_total - total_10d) / total_10d * 100, 2) if total_10d else 0

                if len(dates) >= 21:
                    recent_buys = [combined[d][2] for d in dates[-21:]]
                    avg_20d = sum(recent_buys) / len(recent_buys) if recent_buys else 0
                    fin_buy_heat = round((latest_buy - avg_20d) / avg_20d * 100, 2) if avg_20d else 0
        except Exception:
            pass

        # 融资因子评分
        financing_score += min(max(fin_bal_10d * 3, 0), 18)   # 融资持续扩张=风险累积
        financing_score += min(max(fin_bal_5d * 4, 0), 12)
        if fin_buy_heat < 0:
            financing_score += min(max(abs(fin_buy_heat) * 0.5, 0), 5)  # 买入降温
        financing_score = round(min(financing_score, 35), 1)

        # === 2. 指数趋势因子 (0-30) ===
        trend_score = 0.0
        vol = 0.0
        idx_5d = 0.0
        idx_10d = 0.0
        idx_20d_dd = 0.0
        try:
            def _get_daily_closes(symbol):
                url = f"https://quotes.sina.cn/cn/api/jsonp_v2.php/data/CN_MarketDataService.getKLineData?symbol={symbol}&scale=240&ma=no&datalen=30"
                headers = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://finance.sina.com.cn/'}
                r = requests.get(url, headers=headers, timeout=10, proxies=REQUEST_PROXIES)
                m = re.search(r'data\((.+)\)', r.text, re.DOTALL)
                klines = json.loads(m.group(1)) if m else []
                return [float(k['close']) for k in klines] if klines else []

            sh_c = _get_daily_closes('sh000001')
            sz_c = _get_daily_closes('sz399001')

            # 取沪深平均值
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
                        if c > peak:
                            peak = c
                        dd = (c - peak) / peak * 100
                        if dd < max_dd_20d:
                            max_dd_20d = dd
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

        # === 3. 情绪面因子 (0-20) ===
        sentiment_score = 0.0
        try:
            fear = get_fear_index()
            if fear.get('success') and fear.get('data'):
                fd = fear['data']
                pan = fd.get('score', 50)
                sentiment_score += min(max((pan - 30) * 0.3, 0), 12)
                red = fd.get('red_ratio', 50)
                sentiment_score += min(max((50 - red) * 0.15, 0), 8)
        except Exception:
            pass
        sentiment_score = round(min(sentiment_score, 20), 1)

        # === 4. 涨跌结构因子 (0-15) ===
        limit_score = 0.0
        try:
            # 获取涨停跌停数据
            l_url = "https://push2delay.eastmoney.com/api/qt/clist/get"
            l_params = {
                'pn': 1, 'pz': 1, 'po': 1, 'np': 1, 'fltt': 2, 'invt': 2,
                'fid': 'f3', 'fs': 'm:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23',
                'fields': 'f2,f3,f12,f14',
                'ut': 'b2884a393a59ad64002292a3e90d46a5',
            }
            l_headers = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://data.eastmoney.com/'}
            lr = requests.get(l_url, params=l_params, headers=l_headers, timeout=10, proxies=REQUEST_PROXIES)
            # Use market breadth as rough proxy for limit structure
            bb_url = "https://push2delay.eastmoney.com/api/qt/ulist.np/get"
            bb_params = {
                'fltt': 2, 'invt': 2, 'fields': 'f104,f105,f106',
                'secids': '1.000001,0.399001', 'ut': 'bd1d9ddb04089700cf9c27f6f7426281',
            }
            br = requests.get(bb_url, params=bb_params, headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://data.eastmoney.com/'}, timeout=10, proxies=REQUEST_PROXIES)
            bd = (br.json().get('data') or {}).get('diff') or []
            rise = sum(int(row.get('f104', 0)) for row in bd)
            fall = sum(int(row.get('f105', 0)) for row in bd)
            total = rise + fall
            if total > 0:
                limit_score += min(max(abs(rise - fall) / total * 10, 0), 8)
                limit_score += min(max(fall / total * 15, 0), 7)
        except Exception:
            pass
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

        return {
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
    except Exception as e:
        return {'success': False, 'error': str(e)}


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
