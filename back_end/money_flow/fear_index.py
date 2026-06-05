"""市场恐慌指数"""
import time
import requests
from concurrent.futures import ThreadPoolExecutor
from common import REQUEST_PROXIES
from money_flow.cache import _cache, _cache_set, _cached, _EM_HEADERS, _EM_UT, _MAJOR_INDICES_KEY, _MARKET_BREADTH_KEY, _SH_MINUTE_KEY, _FUND_FLOW_KEY
from money_flow.market import get_sh000001_minute_data
from money_flow.fund_flow import get_market_fund_flow


def get_fear_index():
    """市场恐慌指数：指数走势+日内分时+涨跌面+资金流 多因子加权 0-100"""
    cache_key = 'fear_index'
    cached = _cached(cache_key, 60)
    if cached is not None:
        return cached

    try:
        idx_changes = []
        major_cached = _cache.get(_MAJOR_INDICES_KEY)
        if major_cached and major_cached[0].get('success'):
            for item in major_cached[0]['data']:
                chg_str = item.get('change', '0%')
                try:
                    idx_changes.append(float(chg_str.replace('%', '')))
                except (ValueError, AttributeError):
                    idx_changes.append(0.0)

        minute = None
        sz_intraday = 0.0
        rise = fall = 0
        fund = None

        with ThreadPoolExecutor(max_workers=4) as pool:
            fut_min = pool.submit(get_sh000001_minute_data)
            fut_sz = pool.submit(_fetch_sz_intraday)
            fut_breadth = pool.submit(_fetch_breadth)
            fut_fund = pool.submit(get_market_fund_flow)

            minute = fut_min.result()
            sz_intraday = fut_sz.result()
            rise, fall = fut_breadth.result()
            fund = fut_fund.result()

        avg_idx_change = sum(idx_changes) / len(idx_changes) if idx_changes else 0

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

        total_active = rise + fall
        red_ratio = round(rise / total_active * 100, 1) if total_active > 0 else 50
        down_ratio = round(fall / total_active * 100, 1) if total_active > 0 else 50

        main_net = 0.0
        if fund.get('success') and fund.get('data'):
            flows = fund['data'].get('flows', [])
            main_net = round(flows[-1], 2) if flows else 0

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
    """获取沪深涨跌家数（从后台缓存读取）"""
    cached = _cache.get(_MARKET_BREADTH_KEY)
    if cached:
        return cached[0]
    return 0, 0
