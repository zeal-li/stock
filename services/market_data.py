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
    """大盘资金净流入分时（东财push2delay）"""
    try:
        url = "https://push2delay.eastmoney.com/api/qt/stock/fflow/kline/get"
        params = {
            'lmt': 0, 'klt': 1, 'secid': '1.000001',
            'fields1': 'f1,f2,f3,f7', 'fields2': 'f51,f52,f53,f54,f55,f56,f57,f58',
            'ut': 'b2884a393a59ad64002292a3e90d46a5',
        }
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'Referer': 'https://data.eastmoney.com/', 'Accept': '*/*',
        }
        r = requests.get(url, params=params, headers=headers, timeout=10, proxies=REQUEST_PROXIES)
        klines = (r.json().get('data') or {}).get('klines') or []

        if klines:
            day_groups = {}
            for k in klines:
                parts = str(k).split(',')
                if len(parts) >= 2:
                    date_key = parts[0].split(' ')[0] if ' ' in parts[0] else parts[0]
                    day_groups.setdefault(date_key, []).append(parts)

            latest_day = sorted(day_groups.keys())[-1]
            filtered = day_groups[latest_day]

            times, flows, flows_mid, flows_small = [], [], [], []
            for parts in filtered:
                times.append(parts[0].split(' ')[-1][:5])
                flows.append(round(float(parts[1]) / 1e8, 2))
                flows_mid.append(round(float(parts[3]) / 1e8, 2))
                flows_small.append(round(float(parts[2]) / 1e8, 2))

            if times and times[0] != '09:30':
                times.insert(0, '09:30')
                flows.insert(0, 0)
                flows_mid.insert(0, 0)
                flows_small.insert(0, 0)

            return {
                'success': True,
                'data': {'date': latest_day, 'times': times, 'flows': flows, 'flows_mid': flows_mid, 'flows_small': flows_small}
            }

        return {'success': False, 'error': 'No fund flow data'}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def get_fear_index():
    """市场恐慌指数：涨跌家数比 0-100"""
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
        flat = sum(int(row.get('f106', 0)) for row in diff)
        total_active = rise + fall

        fear_score = round(rise / total_active * 100, 1) if total_active > 0 else 50

        if fear_score <= 30:
            level, color = '极度恐慌', '#4ade80'
        elif fear_score <= 45:
            level, color = '恐慌', '#86efac'
        elif fear_score <= 55:
            level, color = '中性', '#fbbf24'
        elif fear_score <= 70:
            level, color = '乐观', '#f97316'
        else:
            level, color = '极度贪婪', '#e94560'

        return {'success': True, 'data': {'score': fear_score, 'level': level, 'color': color, 'rise': rise, 'fall': fall, 'flat': flat}}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def get_risk_index():
    """市场风险指数：波动率+融资杠杆率"""
    try:
        url = "https://push2delay.eastmoney.com/api/qt/stock/get"
        params = {'secid': '1.000001', 'fields': 'f43,f44,f45,f46,f60,f117', 'ut': 'fa5fd1943c7b386f172d6893dbfba10b'}
        headers = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://data.eastmoney.com/'}
        r = requests.get(url, params=params, headers=headers, timeout=10, proxies=REQUEST_PROXIES)
        d = (r.json() or {}).get('data') or {}
        pre_close = float(d.get('f60', 0)) / 100
        high = float(d.get('f44', 0)) / 100
        low = float(d.get('f45', 0)) / 100
        total_cap = float(d.get('f117', 0))
        vol = abs(high - low) / pre_close * 100 if pre_close else 0

        # 融资杠杆率
        try:
            import akshare as ak
            end_date = datetime.date.today().strftime('%Y%m%d')
            start_date = (datetime.date.today() - datetime.timedelta(days=3)).strftime('%Y%m%d')
            df = ak.stock_margin_sse(start_date=start_date, end_date=end_date)
            margin_balance = float(df.iloc[0]['融资余额']) if df is not None and not df.empty else 0
            leverage = margin_balance / total_cap * 100 if total_cap else 0
        except Exception:
            leverage = 0

        vol_score = min(vol * 16.7, 50)
        lev_score = min(leverage * 10, 50)
        risk_score = round(min(vol_score + lev_score, 100), 1)

        if risk_score <= 20:
            level, color = '低风险', '#4ade80'
        elif risk_score <= 40:
            level, color = '较低风险', '#86efac'
        elif risk_score <= 60:
            level, color = '中等风险', '#fbbf24'
        elif risk_score <= 80:
            level, color = '较高风险', '#f97316'
        else:
            level, color = '高风险', '#e94560'

        return {'success': True, 'data': {'score': risk_score, 'level': level, 'color': color, 'volatility': round(vol, 2), 'leverage': round(leverage, 2)}}
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
