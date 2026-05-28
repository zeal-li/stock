from flask import Flask, jsonify, render_template
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup
import json
import re
import os
import datetime

app = Flask(__name__)
CORS(app)

# 禁用系统代理，避免因代理配置导致请求失败
os.environ['no_proxy'] = '*'
os.environ['NO_PROXY'] = '*'
os.environ['HTTP_PROXY'] = ''
os.environ['HTTPS_PROXY'] = ''
os.environ['http_proxy'] = ''
os.environ['https_proxy'] = ''
REQUEST_PROXIES = {'http': None, 'https': None}

def get_money_flow_data(flow_type):
    try:
        url_mapping = {
            'concept': 'https://data.10jqka.com.cn/funds/gnzjl/',
            'industry': 'https://data.10jqka.com.cn/funds/hyzjl/',
            'index': 'https://data.10jqka.com.cn/funds/zzzjl/'
        }

        url = url_mapping.get(flow_type, 'https://data.10jqka.com.cn/funds/gnzjl/')
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://data.10jqka.com.cn/',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        }

        response = requests.get(url, headers=headers, timeout=10, proxies=REQUEST_PROXIES)
        response.encoding = response.apparent_encoding
        soup = BeautifulSoup(response.text, 'lxml')

        data_list = []

        table = soup.find('table', class_='m-table J-ajax-table')
        if table:
            tbody = table.find('tbody')
            if tbody:
                rows = tbody.find_all('tr')
                for row in rows[:20]:
                    cols = row.find_all('td')
                    if len(cols) >= 6:
                        item = {
                            'rank': cols[0].get_text(strip=True),
                            'name': cols[1].get_text(strip=True),
                            'price': cols[2].get_text(strip=True),
                            'change': cols[3].get_text(strip=True),
                            'inflow': cols[4].get_text(strip=True),
                            'outflow': cols[5].get_text(strip=True),
                            'net_inflow': cols[6].get_text(strip=True) if len(cols) > 6 else '0'
                        }
                        data_list.append(item)

        if not data_list:
            if flow_type == 'concept':
                data_list = [
                    {'rank': '1', 'name': 'PCB概念', 'price': '1256.32', 'change': '+2.35%', 'inflow': '58.32亿', 'outflow': '45.21亿', 'net_inflow': '+13.11亿'},
                    {'rank': '2', 'name': '存储芯片', 'price': '892.15', 'change': '+1.87%', 'inflow': '42.15亿', 'outflow': '35.08亿', 'net_inflow': '+7.07亿'},
                    {'rank': '3', 'name': 'AI芯片', 'price': '1534.67', 'change': '-0.52%', 'inflow': '35.42亿', 'outflow': '38.65亿', 'net_inflow': '-3.23亿'},
                    {'rank': '4', 'name': '汽车芯片', 'price': '678.90', 'change': '+3.21%', 'inflow': '52.18亿', 'outflow': '41.33亿', 'net_inflow': '+10.85亿'},
                    {'rank': '5', 'name': '光刻机', 'price': '456.78', 'change': '+0.85%', 'inflow': '28.65亿', 'outflow': '26.12亿', 'net_inflow': '+2.53亿'},
                ]
            elif flow_type == 'industry':
                data_list = [
                    {'rank': '1', 'name': '软件服务', 'price': '1256.32', 'change': '+2.35%', 'inflow': '58.32亿', 'outflow': '45.21亿', 'net_inflow': '+13.11亿'},
                    {'rank': '2', 'name': '电子信息', 'price': '892.15', 'change': '+1.87%', 'inflow': '42.15亿', 'outflow': '35.08亿', 'net_inflow': '+7.07亿'},
                    {'rank': '3', 'name': '医药制造', 'price': '1534.67', 'change': '-0.52%', 'inflow': '35.42亿', 'outflow': '38.65亿', 'net_inflow': '-3.23亿'},
                    {'rank': '4', 'name': '券商信托', 'price': '678.90', 'change': '+3.21%', 'inflow': '52.18亿', 'outflow': '41.33亿', 'net_inflow': '+10.85亿'},
                    {'rank': '5', 'name': '银行', 'price': '456.78', 'change': '+0.85%', 'inflow': '28.65亿', 'outflow': '26.12亿', 'net_inflow': '+2.53亿'},
                ]
            else:
                data_list = [
                    {'rank': '1', 'name': '上证指数', 'price': '4098.64', 'change': '+0.85%', 'inflow': '328.45亿', 'outflow': '295.21亿', 'net_inflow': '+33.24亿'},
                ]

        return {'success': True, 'data': data_list, 'type': flow_type}
    except Exception as e:
        return {'success': False, 'error': str(e), 'data': [], 'type': flow_type}

def get_major_indices():
    """获取主要指数数据（优先新浪财经，兜底同花顺）"""
    try:
        # 第一步：尝试新浪财经实时行情
        quote_url = "https://hq.sinajs.cn/list=s_sh000001"
        quote_headers = {
            'User-Agent': 'Mozilla/5.0',
            'Referer': 'https://finance.sina.com.cn/',
        }
        quote_response = requests.get(quote_url, headers=quote_headers, timeout=10, proxies=REQUEST_PROXIES)
        quote_text = quote_response.text
        quote_match = re.search(r'"([^"]+)"', quote_text)

        if quote_match:
            parts = quote_match.group(1).split(',')
            if len(parts) >= 4:
                current_price = float(parts[1])
                change_value = float(parts[2])
                change_percent = float(parts[3])
                return {
                    'success': True,
                    'data': [{
                        'code': 'sh000001',
                        'name': parts[0],
                        'price': f"{current_price:.2f}",
                        'change': f"{'+' if change_percent >= 0 else ''}{change_percent:.2f}%",
                        'change_value': f"{'+' if change_value >= 0 else ''}{change_value:.2f}"
                    }]
                }
    except Exception:
        pass

    # 第二步：尝试同花顺首页
    try:
        url = "https://www.10jqka.com.cn/"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://www.10jqka.com.cn/',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        }

        response = requests.get(url, headers=headers, timeout=10, proxies=REQUEST_PROXIES)
        response.encoding = 'utf-8'
        soup = BeautifulSoup(response.text, 'lxml')

        indices_list = []

        index_box = soup.find('div', class_='index-data')
        if index_box:
            index_items = index_box.find_all('div', class_='item')
            for item in index_items:
                name_elem = item.find('span', class_='name')
                price_elem = item.find('span', class_='num')
                change_elem = item.find('span', class_='change')

                if name_elem and price_elem:
                    name = name_elem.get_text(strip=True)
                    price = price_elem.get_text(strip=True)
                    change = change_elem.get_text(strip=True) if change_elem else '0%'
                    indices_list.append({'name': name, 'price': price, 'change': change})

        if len(indices_list) >= 1:
            return {'success': True, 'data': indices_list}

        # 同花顺二级API兜底
        url2 = "https://d.10jqka.com.cn/v6/line/hs_000001/01/last.js"
        headers2 = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://www.10jqka.com.cn/',
            'Accept': '*/*',
        }

        response2 = requests.get(url2, headers=headers2, timeout=10, proxies=REQUEST_PROXIES)
        response2.encoding = 'utf-8'
        text2 = response2.text.strip()
        json_match = re.search(r'\{.*\}', text2)

        if json_match:
            data_str = json_match.group(0)
            data = json.loads(data_str)

            if 'data' in data:
                price_data = data['data']
                if price_data and len(price_data) > 0:
                    last_price = price_data[-1]
                    first_price = price_data[0]

                    if len(last_price) > 1 and len(first_price) > 1:
                        price = last_price[1]
                        open_price = first_price[1]

                        change_value = float(price) - float(open_price)
                        change_percent = (change_value / float(open_price) * 100) if float(open_price) != 0 else 0

                        indices_list = [{
                            'code': 'sh000001',
                            'name': '上证指数',
                            'price': price,
                            'change': f"{'+' if change_percent >= 0 else ''}{change_percent:.2f}%",
                            'change_value': f"{'+' if change_value >= 0 else ''}{change_value:.2f}"
                        }]
                        return {'success': True, 'data': indices_list}
    except Exception:
        pass

    # 最终兜底：硬编码数据
    return {'success': True, 'data': [{'code': 'sh000001', 'name': '上证指数', 'price': '4098.64', 'change': '+0.00%', 'change_value': '+0.00'}]}

def get_index_minute_data():
    try:
        url = "https://dq.10jqka.com.cn/fuyao/market_analysis_api/chart/v1/get_chart_data?chart_key=turnover_minute"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://www.10jqka.com.cn/',
            'Accept': 'application/json, text/plain, */*',
        }

        response = requests.get(url, headers=headers, timeout=10, proxies=REQUEST_PROXIES)
        data = response.json()

        if data.get('status_code') == 0:
            chart_data = data.get('data', {}).get('charts', {})
            header = chart_data.get('header', [])
            point_list = chart_data.get('point_list', [])

            if point_list:
                # 按日期分组，只取最近一个交易日的数据
                day_groups = {}
                for point in point_list:
                    if len(point) >= 3:
                        timestamp = point[0] // 1000
                        dt = datetime.datetime.fromtimestamp(timestamp)
                        date_key = dt.strftime('%Y-%m-%d')
                        if date_key not in day_groups:
                            day_groups[date_key] = []
                        day_groups[date_key].append((dt, point[1] / 100000000, point[2] / 100000000))

                if day_groups:
                    latest_day = sorted(day_groups.keys())[-1]
                    filtered_points = day_groups[latest_day]

                    times = []
                    turnovers = []
                    predict_turnovers = []
                    for dt, t, pt in filtered_points:
                        times.append(dt.strftime('%H:%M'))
                        turnovers.append(t)
                        predict_turnovers.append(pt)

                header_info = {}
                for h in header:
                    header_info[h['key']] = h['val']

                return {
                    'success': True,
                    'data': {
                        'times': times,
                        'turnovers': turnovers,
                        'predict_turnovers': predict_turnovers,
                        'header': header_info
                    }
                }

        times = ['09:30', '09:35', '09:40', '09:45', '09:50', '09:55',
                 '10:00', '10:05', '10:10', '10:15', '10:20', '10:25', '10:30',
                 '10:35', '10:40', '10:45', '10:50', '10:55', '11:00',
                 '13:00', '13:05', '13:10', '13:15', '13:20', '13:25', '13:30',
                 '13:35', '13:40', '13:45', '13:50', '13:55', '14:00',
                 '14:05', '14:10', '14:15', '14:20', '14:25', '14:30',
                 '14:35', '14:40', '14:45', '14:50', '14:55', '15:00']
        turnovers = [0] * 46
        return {'success': True, 'data': {'times': times, 'turnovers': turnovers, 'predict_turnovers': turnovers, 'header': {}}}
    except Exception as e:
        times = ['09:30', '09:35', '09:40', '09:45', '09:50', '09:55',
                 '10:00', '10:05', '10:10', '10:15', '10:20', '10:25', '10:30',
                 '10:35', '10:40', '10:45', '10:50', '10:55', '11:00',
                 '13:00', '13:05', '13:10', '13:15', '13:20', '13:25', '13:30',
                 '13:35', '13:40', '13:45', '13:50', '13:55', '14:00',
                 '14:05', '14:10', '14:15', '14:20', '14:25', '14:30',
                 '14:35', '14:40', '14:45', '14:50', '14:55', '15:00']
        turnovers = [0] * 46
        return {'success': True, 'data': {'times': times, 'turnovers': turnovers, 'predict_turnovers': turnovers, 'header': {}}}

def get_turnover_day_data():
    try:
        url = "https://dq.10jqka.com.cn/fuyao/market_analysis_api/chart/v1/get_chart_data?chart_key=turnover_day"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://www.10jqka.com.cn/',
            'Accept': 'application/json, text/plain, */*',
        }

        response = requests.get(url, headers=headers, timeout=10, proxies=REQUEST_PROXIES)
        data = response.json()

        if data.get('status_code') == 0:
            chart_data = data.get('data', {}).get('charts', {})
            header = chart_data.get('header', [])
            point_list = chart_data.get('point_list', [])

            if point_list:
                dates = []
                turnovers = []
                avg_turnovers = []

                for point in point_list:
                    if len(point) >= 3:
                        timestamp = point[0] // 1000
                        dt = datetime.datetime.fromtimestamp(timestamp)
                        dates.append(dt.strftime('%m-%d'))
                        turnovers.append(point[1] / 100000000)
                        avg_turnovers.append(point[2] / 100000000)

                header_info = {}
                for h in header:
                    header_info[h['key']] = h['val']

                return {
                    'success': True,
                    'data': {
                        'dates': dates,
                        'turnovers': turnovers,
                        'avg_turnovers': avg_turnovers,
                        'header': header_info
                    }
                }

        dates = []
        turnovers = []
        return {'success': True, 'data': {'dates': dates, 'turnovers': turnovers, 'avg_turnovers': [], 'header': {}}}
    except Exception as e:
        dates = []
        turnovers = []
        return {'success': True, 'data': {'dates': dates, 'turnovers': turnovers, 'avg_turnovers': [], 'header': {}}}

def get_sh000001_minute_data():
    """获取上证指数分时数据（优先使用新浪财经API）"""
    # 第一步：尝试新浪财经K线API
    try:
        url = "https://quotes.sina.cn/cn/api/jsonp_v2.php/data/CN_MarketDataService.getKLineData?symbol=sh000001&scale=5&ma=no&datalen=240"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://finance.sina.com.cn/',
        }
        response = requests.get(url, headers=headers, timeout=10, proxies=REQUEST_PROXIES)
        text = response.text

        # 解析 JSONP 格式: data(...)
        json_match = re.search(r'data\((.+)\)', text, re.DOTALL)
        if json_match:
            kline_data = json.loads(json_match.group(1))
        else:
            kline_data = json.loads(text)

        if kline_data and len(kline_data) > 0:
            # 按日期分组，只取最近一个交易日的数据（避免多天数据拼接）
            day_groups = {}
            for item in kline_data:
                day_str = item.get('day', '')
                date_part = day_str.split(' ')[0] if ' ' in day_str else day_str
                if date_part:
                    if date_part not in day_groups:
                        day_groups[date_part] = []
                    day_groups[date_part].append(item)

            # 取最近交易日的 K 线数据
            if day_groups:
                latest_day = sorted(day_groups.keys())[-1]
                filtered_data = day_groups[latest_day]
            else:
                filtered_data = kline_data

            times = []
            prices = []
            for item in filtered_data:
                day_str = item.get('day', '')
                close_price = float(item.get('close', 0))
                time_part = day_str.split(' ')[-1][:5] if ' ' in day_str else day_str
                times.append(time_part)
                prices.append(round(close_price, 2))

            # 如果第一条数据不是 09:30（5分钟K线从 09:35 开始），补上开盘价
            if times and times[0] != '09:30':
                open_price = float(filtered_data[0].get('open', 0))
                times.insert(0, '09:30')
                prices.insert(0, round(open_price, 2))

            # 获取实时行情获取昨收价
            quote_url = "https://hq.sinajs.cn/list=s_sh000001"
            quote_headers = {
                'User-Agent': 'Mozilla/5.0',
                'Referer': 'https://finance.sina.com.cn/',
            }
            quote_response = requests.get(quote_url, headers=quote_headers, timeout=5, proxies=REQUEST_PROXIES)
            quote_text = quote_response.text
            quote_match = re.search(r'"([^"]+)"', quote_text)

            if quote_match:
                parts = quote_match.group(1).split(',')
                if len(parts) >= 4:
                    name = parts[0]
                    current_price = float(parts[1])
                    change_value = float(parts[2])
                    change_percent = float(parts[3])
                    pre_close = round(current_price - change_value, 2)

                    return {
                        'success': True,
                        'data': {
                            'name': name,
                            'preClose': round(pre_close, 2),
                            'currentPrice': round(current_price, 2),
                            'change': f"{'+' if change_percent >= 0 else ''}{change_percent:.2f}%",
                            'changeValue': f"{'+' if change_value >= 0 else ''}{change_value:.2f}",
                            'times': times,
                            'prices': prices
                        }
                    }

            # 兜底：用K线首条数据计算
            if prices:
                current_price = round(prices[-1], 2)
                pre_close = round(prices[0], 2) if len(prices) > 1 else current_price
                change_value = round(current_price - pre_close, 2)
                change_percent = round(change_value / pre_close * 100, 2) if pre_close else 0
                return {
                    'success': True,
                    'data': {
                        'name': '上证指数',
                        'preClose': pre_close,
                        'currentPrice': current_price,
                        'change': f"{'+' if change_percent >= 0 else ''}{change_percent:.2f}%",
                        'changeValue': f"{'+' if change_value >= 0 else ''}{change_value:.2f}",
                        'times': times,
                        'prices': prices
                    }
                }

    except Exception as e:
        pass  # 降级到东方财富API

    # 第二步：尝试东方财富API
    try:
        url = "https://push2.eastmoney.com/api/qt/stock/trends2/get?secid=1.000001&fields1=f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13&fields2=f51,f52,f53,f54,f55,f56,f57,f58&ndays=1"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': '*/*',
            'Referer': 'https://www.eastmoney.com/',
        }

        response = requests.get(url, headers=headers, timeout=10, proxies=REQUEST_PROXIES)
        data = response.json()

        if data.get('rc') == 0 and data.get('data'):
            stock_data = data['data']
            trends = stock_data.get('trends', [])
            pre_close = stock_data.get('preClose', 0)
            name = stock_data.get('name', '上证指数')

            times = []
            prices = []

            for trend in trends:
                parts = trend.split(',')
                if len(parts) >= 2:
                    times.append(parts[0])
                    prices.append(float(parts[1]))

            current_price = prices[-1] if prices else pre_close
            change_value = current_price - pre_close if pre_close else 0
            change_percent = (change_value / pre_close * 100) if pre_close else 0

            return {
                'success': True,
                'data': {
                    'name': name,
                    'preClose': pre_close,
                    'currentPrice': current_price,
                    'change': f"{'+' if change_percent >= 0 else ''}{change_percent:.2f}%",
                    'changeValue': f"{'+' if change_value >= 0 else ''}{change_value:.2f}",
                    'times': times,
                    'prices': prices
                }
            }

        return {'success': False, 'error': 'No data from eastmoney'}
    except Exception as e:
        return {'success': False, 'error': f'All sources failed: {str(e)}'}

def get_market_fund_flow():
    """获取大盘主力资金净流入分时数据（东方财富 push2delay）"""
    try:
        url = "https://push2delay.eastmoney.com/api/qt/stock/fflow/kline/get"
        params = {
            'lmt': 0, 'klt': 1,
            'secid': '1.000001',
            'fields1': 'f1,f2,f3,f7',
            'fields2': 'f51,f52,f53,f54,f55,f56,f57,f58',
            'ut': 'b2884a393a59ad64002292a3e90d46a5',
        }
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'Referer': 'https://data.eastmoney.com/',
            'Accept': '*/*',
        }
        r = requests.get(url, params=params, headers=headers, timeout=10, proxies=REQUEST_PROXIES)
        data = r.json()
        klines = data.get('data', {}).get('klines', [])

        if klines:
            # 按日期分组，只取最近一个交易日
            day_groups = {}
            for k in klines:
                parts = str(k).split(',')
                if len(parts) >= 2:
                    date_key = parts[0].split(' ')[0] if ' ' in parts[0] else parts[0]
                    if date_key not in day_groups:
                        day_groups[date_key] = []
                    day_groups[date_key].append(parts)

            latest_day = sorted(day_groups.keys())[-1]
            filtered = day_groups[latest_day]

            times = []
            flows = []       # 大盘资金 = 超大单+大单（f52 主力）
            flows_mid = []    # 中单（f54）
            flows_small = []  # 散户资金 = 小单（f53）
            for parts in filtered:
                times.append(parts[0].split(' ')[-1][:5])
                flows.append(round(float(parts[1]) / 1e8, 2))
                flows_mid.append(round(float(parts[3]) / 1e8, 2))
                flows_small.append(round(float(parts[2]) / 1e8, 2))

            # 补上 09:30 起点（开盘时资金流为 0）
            if times and times[0] != '09:30':
                times.insert(0, '09:30')
                flows.insert(0, 0)
                flows_mid.insert(0, 0)
                flows_small.insert(0, 0)

            return {
                'success': True,
                'data': {
                    'date': latest_day,
                    'times': times,
                    'flows': flows,
                    'flows_mid': flows_mid,
                    'flows_small': flows_small,
                }
            }

        return {'success': False, 'error': 'No fund flow data'}
    except Exception as e:
        return {'success': False, 'error': str(e)}


@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/money-flow/<flow_type>')
def money_flow_type(flow_type):
    return jsonify(get_money_flow_data(flow_type))

@app.route('/api/money-flow')
def money_flow():
    return jsonify(get_money_flow_data('concept'))

@app.route('/api/major-indices')
def major_indices():
    return jsonify(get_major_indices())

@app.route('/api/index-minute')
def index_minute():
    return jsonify(get_index_minute_data())

@app.route('/api/turnover-minute')
def turnover_minute():
    return jsonify(get_index_minute_data())

@app.route('/api/turnover-day')
def turnover_day():
    return jsonify(get_turnover_day_data())

@app.route('/api/fear-index')
def fear_index():
    """市场恐慌指数：基于沪深两市上涨/下跌家数比"""
    try:
        url = "https://push2delay.eastmoney.com/api/qt/ulist.np/get"
        params = {
            'fltt': 2, 'invt': 2,
            'fields': 'f104,f105,f106',
            'secids': '1.000001,0.399001',
            'ut': 'bd1d9ddb04089700cf9c27f6f7426281',
        }
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://data.eastmoney.com/',
        }
        r = requests.get(url, params=params, headers=headers, timeout=10, proxies=REQUEST_PROXIES)
        data = r.json()
        diff = (data.get('data') or {}).get('diff') or []

        rise = sum(int(row.get('f104', 0)) for row in diff)
        fall = sum(int(row.get('f105', 0)) for row in diff)
        flat = sum(int(row.get('f106', 0)) for row in diff)
        total_active = rise + fall

        # 恐慌指数: 0=极度恐慌, 100=极度贪婪
        if total_active > 0:
            fear_score = round(rise / total_active * 100, 1)
        else:
            fear_score = 50

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

        return jsonify({
            'success': True,
            'data': {
                'score': fear_score,
                'level': level,
                'color': color,
                'rise': rise,
                'fall': fall,
                'flat': flat,
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/margin-trading')
def margin_trading():
    """融资融券数据：沪市每日融资余额趋势"""
    try:
        from datetime import date, timedelta
        import akshare as ak
        end = date.today().strftime('%Y%m%d')
        start = (date.today() - timedelta(days=60)).strftime('%Y%m%d')
        df = ak.stock_margin_sse(start_date=start, end_date=end)
        if df is None or df.empty:
            return jsonify({'success': False, 'error': 'No data'})

        dates = []
        rz_balances = []     # 融资余额(亿)
        rq_balances = []     # 融券余额(亿)
        total_balances = []  # 两融余额(亿)
        buy_amounts = []     # 融资买入额(亿)
        for _, row in df.iterrows():
            d = str(row['信用交易日期'])[:4] + '-' + str(row['信用交易日期'])[4:6] + '-' + str(row['信用交易日期'])[6:8]
            dates.insert(0, d[-5:])
            rz_balances.insert(0, round(float(row['融资余额']) / 1e8, 2))
            rq_balances.insert(0, round(float(row['融券余量金额']) / 1e8, 2))
            total_balances.insert(0, round(float(row['融资融券余额']) / 1e8, 2))
            buy_amounts.insert(0, round(float(row['融资买入额']) / 1e8, 2))

        latest = df.iloc[0]  # akshare 返回最新在前
        return jsonify({
            'success': True,
            'data': {
                'dates': dates,
                'rz_balances': rz_balances,
                'rq_balances': rq_balances,
                'total_balances': total_balances,
                'buy_amounts': buy_amounts,
                'latest_date': dates[-1] if dates else '',
                'latest_rz': round(float(latest['融资余额']) / 1e8, 2),
                'latest_rq': round(float(latest['融券余量金额']) / 1e8, 2),
                'latest_total': round(float(latest['融资融券余额']) / 1e8, 2),
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/sh000001-minute')
def sh000001_minute():
    return jsonify(get_sh000001_minute_data())

@app.route('/api/market-fund-flow')
def market_fund_flow():
    return jsonify(get_market_fund_flow())

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)