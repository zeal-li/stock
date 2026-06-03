"""资金流向：成交额分时/日线"""
import datetime
import requests
from . import REQUEST_PROXIES


def get_index_minute_data():
    """成交额分时数据"""
    url = "https://dq.10jqka.com.cn/fuyao/market_analysis_api/chart/v1/get_chart_data?chart_key=turnover_minute"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': 'https://www.10jqka.com.cn/',
        'Accept': 'application/json, text/plain, */*',
    }
    resp = requests.get(url, headers=headers, timeout=10, proxies=REQUEST_PROXIES)
    data = resp.json()
    if data.get('status_code') != 0:
        return {'success': False, 'error': '同花顺成交额分时 status_code != 0'}
    chart_data = data.get('data', {}).get('charts', {})
    header = chart_data.get('header', [])
    point_list = chart_data.get('point_list', [])
    if not point_list:
        return {'success': False, 'error': '同花顺成交额分时无 point_list'}

    day_groups = {}
    for point in point_list:
        if len(point) >= 3 and point[1] is not None and point[2] is not None:
            timestamp = point[0] // 1000
            dt = datetime.datetime.fromtimestamp(timestamp)
            date_key = dt.strftime('%Y-%m-%d')
            day_groups.setdefault(date_key, []).append((dt, point[1] / 1e8, point[2] / 1e8))

    if not day_groups:
        return {'success': False, 'error': '同花顺成交额分时无交易日数据'}
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


def get_turnover_day_data():
    """成交额日数据"""
    url = "https://dq.10jqka.com.cn/fuyao/market_analysis_api/chart/v1/get_chart_data?chart_key=turnover_day"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': 'https://www.10jqka.com.cn/',
        'Accept': 'application/json, text/plain, */*',
    }
    resp = requests.get(url, headers=headers, timeout=10, proxies=REQUEST_PROXIES)
    data = resp.json()
    if data.get('status_code') != 0:
        return {'success': False, 'error': '同花顺成交额日线 status_code != 0'}
    chart_data = data.get('data', {}).get('charts', {})
    header = chart_data.get('header', [])
    point_list = chart_data.get('point_list', [])
    if not point_list:
        return {'success': False, 'error': '同花顺成交额日线无 point_list'}

    dates, turnovers, avg_turnovers = [], [], []
    for point in point_list:
        if len(point) >= 3:
            timestamp = point[0] // 1000
            dt = datetime.datetime.fromtimestamp(timestamp)
            dates.append(dt.strftime('%m-%d'))
            turnovers.append(point[1] / 1e8)
            avg_turnovers.append(point[2] / 1e8)

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
