"""强势回调选股策略 — 多因子共振筛选明日上涨概率较高的股票

核心思路：处于上升趋势的强势股回调到均线支撑位，缩量止跌企稳，
          多因子共振时大概率次日反弹。

五大因子：
  1. 均线趋势 — 均线多头排列，中长期趋势向上
  2. 回调到位 — 从近期高点适度回调，回踩关键均线
  3. 量价配合 — 上涨放量、回调缩量，资金运作痕迹
  4. 动能确认 — 短期温和上涨，今日收阳止跌
  5. 位置安全 — 不在高位追涨，不在低位弱势

选取标准：至少满足均线趋势 + 量价配合两项硬条件，综合评分 >= 50
"""


def calc(klines, lookback=60):
    if len(klines) < max(lookback, 60):
        return 0, {}

    window = klines[-lookback:]
    closes = [k['close'] for k in window]
    opens = [k['open'] for k in window]
    highs = [k['high'] for k in window]
    lows = [k['low'] for k in window]
    volumes = [k['volume'] for k in window]

    latest = window[-1]
    cur_close = closes[-1]
    cur_open = opens[-1]

    # ====== 计算均线 ======
    def _ma(data, period):
        if len(data) < period:
            return None
        return sum(data[-period:]) / period

    ma5 = _ma(closes, 5)
    ma10 = _ma(closes, 10)
    ma20 = _ma(closes, 20)
    ma60 = _ma(closes, 60)

    if ma5 is None or ma10 is None or ma20 is None:
        return 0, {}

    # ====== 1. 均线趋势 (25分) ======
    # 硬性条件：必须在 MA20 上方，否则趋势不成立
    if cur_close <= ma20:
        return 0, {}

    ma_bullish = ma5 > ma10 > ma20
    ma_60_ok = ma60 is None or ma20 > ma60

    ma_score = 0
    if ma_bullish:
        ma_score += 18
    if ma_60_ok:
        ma_score += 4
    if ma5 > ma20 * 1.03:
        ma_score += 3

    # ====== 2. 回调检测 (25分) ======
    high_10 = max(highs[-10:])
    pullback_10 = (high_10 - cur_close) / high_10
    dist_ma10 = (cur_close - ma10) / ma10
    dist_ma20 = (cur_close - ma20) / ma20

    pullback_score = 0
    is_pulling_back = 0.03 <= pullback_10 <= 0.12
    near_ma10 = abs(dist_ma10) <= 0.025
    near_ma20 = abs(dist_ma20) <= 0.03

    if is_pulling_back:
        pullback_score += 10
        if near_ma10:
            pullback_score += 12
        elif near_ma20:
            pullback_score += 6
    elif not is_pulling_back and near_ma10 and dist_ma10 >= -0.01:
        # 未明显回调但在 MA10 附近横盘蓄力
        pullback_score += 6
    elif not is_pulling_back and near_ma20 and dist_ma20 >= -0.01:
        pullback_score += 3

    if 0.03 <= pullback_10 <= 0.08:
        pullback_score += 3

    # ====== 3. 量价配合 (25分) ======
    avg_vol_20 = sum(volumes[-21:-1]) / 20
    if avg_vol_20 <= 0:
        return 0, {}

    # 近 10 天内是否有放量上涨日（量 > 1.3 倍均量 且 收阳线）
    has_vol_break = False
    for i in range(-10, 0):
        dv = volumes[i]
        dc = closes[i]
        do_ = opens[i]
        if dv > avg_vol_20 * 1.3 and dc >= do_:
            has_vol_break = True
            break

    # 近 3 天缩量天数（量 < 均量 85%）
    shrink_days = sum(1 for i in range(-3, 0) if volumes[i] < avg_vol_20 * 0.85)

    today_vol_ratio = latest['volume'] / avg_vol_20
    today_is_up = cur_close >= cur_open

    vol_score = 0
    if has_vol_break:
        vol_score += 18
    if shrink_days >= 2:
        vol_score += 7
    # 今日温和放量收阳加分
    if today_is_up and 0.6 <= today_vol_ratio <= 1.5:
        vol_score += 5

    # 硬性条件：必须至少有一项量价信号
    if not has_vol_break and shrink_days == 0:
        return 0, {}

    # ====== 4. 动能确认 (15分) ======
    chg_5d = (closes[-1] - closes[-6]) / closes[-6] if len(closes) >= 6 else 0
    chg_10d = (closes[-1] - closes[-11]) / closes[-11] if len(closes) >= 11 else 0

    body = cur_close - cur_open
    body_pct = abs(body) / cur_open if cur_open > 0 else 0

    momentum_score = 0
    if 0.005 < chg_5d <= 0.08:
        momentum_score += 8
    elif 0 < chg_5d <= 0.005:
        momentum_score += 4
    if chg_10d > 0.01:
        momentum_score += 4
    if body >= 0 and body_pct > 0.003:
        momentum_score += 3

    # 硬性条件：5 日不能大跌
    if chg_5d < -0.06:
        return 0, {}

    # ====== 5. 位置安全 (10分) ======
    high_60 = max(highs) if len(highs) <= 60 else max(highs[-60:])
    low_60 = min(lows) if len(lows) <= 60 else min(lows[-60:])
    pos_60 = (cur_close - low_60) / (high_60 - low_60) if high_60 > low_60 else 0.5

    position_score = 0
    # 不高（< 85%分位）
    if pos_60 < 0.85:
        position_score += 5
    # 不弱（> 25%分位）
    if pos_60 > 0.25:
        position_score += 5

    # ====== 综合评分 ======
    total = ma_score + pullback_score + vol_score + momentum_score + position_score
    if total < 50:
        return 0, {}

    score = round(min(total, 100), 1)

    detail = {
        'ma_bullish': ma_bullish,
        'pullback_pct': round(pullback_10 * 100, 1),
        'dist_ma10_pct': round(dist_ma10 * 100, 1),
        'dist_ma20_pct': round(dist_ma20 * 100, 1),
        'has_vol_break': has_vol_break,
        'shrink_days': shrink_days,
        'today_vol_ratio': round(today_vol_ratio, 2),
        'chg_5d': round(chg_5d * 100, 2),
        'chg_10d': round(chg_10d * 100, 2),
        'pos_60': round(pos_60 * 100, 1),
        'ma5': round(ma5, 2),
        'ma10': round(ma10, 2),
        'ma20': round(ma20, 2),
        'score_breakdown': {
            'ma': ma_score,
            'pullback': pullback_score,
            'vol': vol_score,
            'momentum': momentum_score,
            'position': position_score,
        },
    }

    return score, detail
