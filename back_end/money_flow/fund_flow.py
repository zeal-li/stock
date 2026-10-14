"""大盘资金净流入"""
import datetime
from common.http import get_em_fflow_kline
from money_flow.storage import save_field, get_field


def _fetch_and_cache_fund_flow():
    """抓取大盘资金净流入分时并写入缓存（沪深两市合计，走浏览器 JSONP）"""
    try:
        def _fetch(secid):
            klines = get_em_fflow_kline(secid)
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
        save_field('fund_flow', result)
        return True
    except Exception as e:
        print(f"[fund-flow poller] fetch error: {e}")
    return False


def get_market_fund_flow():
    """大盘资金净流入分时（优先读快照，快照空时同步抓取）"""
    val = get_field('fund_flow')
    if val:
        return val
    _fetch_and_cache_fund_flow()
    val = get_field('fund_flow')
    if val:
        return val
    return {'success': False, 'error': '暂无资金流数据'}
