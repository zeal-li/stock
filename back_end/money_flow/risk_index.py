"""市场风险指数"""
import time
from concurrent.futures import ThreadPoolExecutor
from money_flow.storage import db_get, _cache_set, _cached, _MARGIN_KEY, _MARKET_BREADTH_KEY, _DAILY_CLOSES_KEY


def get_risk_index():
    """市场风险指数：融资杠杆+指数趋势+情绪面+涨跌结构 多因子加权 0-100"""
    cache_key = 'risk_index'
    cached = _cached(cache_key, 60)
    if cached is not None:
        return cached

    try:
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

        # === 3. 情绪面因子 (0-20) ===
        sentiment_score = 0.0
        try:
            red_ratio = round(rise / (rise + fall) * 100, 1) if (rise + fall) > 0 else 50
            sentiment_score += min(max((50 - red_ratio) * 0.3, 0), 12)
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
    """获取融资因子数据（从后台融资融券缓存读取）"""
    cached = db_get(_MARGIN_KEY)
    if cached and cached[0].get('success'):
        d = cached[0]['data']
        return {
            'fin_bal_5d': d.get('fin_bal_5d', 0.0),
            'fin_bal_10d': d.get('fin_bal_10d', 0.0),
            'fin_buy_heat': d.get('fin_buy_heat', 0.0),
        }
    return {}


def _fetch_daily_closes(symbol):
    """获取日线收盘价（从后台缓存读取）"""
    cached = db_get(_DAILY_CLOSES_KEY)
    if cached:
        return cached[0].get(symbol, [])
    return []


def _fetch_breadth():
    """获取沪深涨跌家数"""
    cached = db_get(_MARKET_BREADTH_KEY)
    if cached:
        return cached[0]
    return 0, 0


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
