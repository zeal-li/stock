"""大盘资金净流入"""
import datetime
import time
import requests
from common import REQUEST_PROXIES
from money_flow.storage import db_set, db_get, _FUND_FLOW_KEY


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
        db_set(_FUND_FLOW_KEY, result, time.time())
        return True
    except Exception as e:
        print(f"[fund-flow poller] fetch error: {e}")
    return False


def get_market_fund_flow():
    """大盘资金净流入分时（优先读缓存，缓存空时同步抓取）"""
    row = db_get(_FUND_FLOW_KEY)
    if row:
        return row[0]
    _fetch_and_cache_fund_flow()
    row = db_get(_FUND_FLOW_KEY)
    if row:
        return row[0]
    return {'success': False, 'error': '暂无资金流数据'}
