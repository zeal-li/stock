"""成交额分时数据"""
import datetime
import time
import requests
from common import REQUEST_PROXIES
from money_flow.cache import _cache, _TURNOVER_MINUTE_KEY


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
