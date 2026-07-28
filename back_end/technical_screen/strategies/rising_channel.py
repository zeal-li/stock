"""上升通道选股策略 — 日K/周K/月K布林中上轨共振

核心思路（参考 600900 2023-06 ~ 2024-07）：
  股价突破布林中轨后稳定运行在中轨到上轨之间，布林中轨温和向上倾斜，
  盘中回踩不破前低（一底比一底高），跌破中轨后能快速修复，无极端涨跌。

硬条件：
  1. 三周期阶段性低点一底比一底高（至少 2 个周期，这是核心特征）
  2. 三周期布林中轨向上倾斜，坡度不过陡
  3. 三周期大部分时间在中上轨（日 >= 40%，周 >= 40%，月 >= 35%）
  4. 跌破中轨后能在合理时间内修复（日 <= 12天，周 <= 10周，月 <= 8月）
  5. 无涨跌停等极端行情
"""


def _lr_slope(values):
    n = len(values)
    x = list(range(n))
    sx = sum(x)
    sy = sum(values)
    sxy = sum(x[i] * values[i] for i in range(n))
    sx2 = sum(v ** 2 for v in x)
    d = n * sx2 - sx * sx
    if d == 0:
        return 0
    return (n * sxy - sx * sy) / d


def _calc_bb(klines, period=20):
    closes = [k['close'] for k in klines[-period:]]
    ma = sum(closes) / period
    var = sum((c - ma) ** 2 for c in closes) / period
    std = var ** 0.5
    upper = ma + 2 * std
    mid = ma
    lower = ma - 2 * std
    return {'upper': upper, 'mid': mid, 'lower': lower}


def _ascending_lows(klines, segments=4):
    """检测阶段性低点是否一底比一底高"""
    n = len(klines)
    seg_size = n // segments
    if seg_size < 3:
        return False, []

    lows = []
    for s in range(segments):
        start = s * seg_size
        end = start + seg_size if s < segments - 1 else n
        seg_closes = [k['close'] for k in klines[start:end]]
        lows.append(min(seg_closes))

    ascending = True
    for i in range(1, len(lows)):
        if lows[i] < lows[i - 1] * 0.995:
            ascending = False
            break
    return ascending, lows


def _upper_half_analysis(klines, bb_period=20, ratio_period=20):
    closes_all = [k['close'] for k in klines]
    bb = _calc_bb(klines, bb_period)
    mid = bb['mid']
    upper = bb['upper']

    recent = closes_all[-ratio_period:]
    in_upper = sum(1 for c in recent if c >= mid)
    ratio = in_upper / len(recent)

    max_consecutive_below = 0
    current_streak = 0
    for c in recent:
        if c < mid:
            current_streak += 1
            max_consecutive_below = max(max_consecutive_below, current_streak)
        else:
            current_streak = 0

    recent5 = closes_all[-5:]
    was_below = any(c < mid for c in recent5[:-1])
    now_above = closes_all[-1] >= mid
    recovering = was_below and now_above

    slope = _lr_slope(closes_all[-bb_period:])
    slope_pct = slope / mid if mid > 0 else 0

    return {
        'ratio': ratio,
        'max_below_days': max_consecutive_below,
        'recovering': recovering,
        'mid': mid,
        'upper': upper,
        'slope': slope,
        'slope_pct': slope_pct,
    }


def calc(daily_klines, weekly_klines=None, monthly_klines=None, lookback=60):
    dk = daily_klines
    wk = weekly_klines or []
    mk = monthly_klines or []

    if len(dk) < 60 or len(wk) < 20 or len(mk) < 12:
        return 0, {}

    # ====== 各周期分析 ======
    da = _upper_half_analysis(dk, bb_period=20, ratio_period=20)
    wa = _upper_half_analysis(wk, bb_period=20, ratio_period=20)
    ma = _upper_half_analysis(mk, bb_period=20, ratio_period=12)

    # ====== 硬条件0: 一底比一底高（核心特征，至少 2 个周期） ======
    d_asc, d_lows = _ascending_lows(dk[-60:], 4)
    w_asc, w_lows = _ascending_lows(wk[-20:], 4)
    m_asc, m_lows = _ascending_lows(mk[-12:], 3) if len(mk) >= 12 else (False, [])

    asc_count = sum([d_asc, w_asc, m_asc])
    if asc_count < 2:
        return 0, {}

    # ====== 硬条件1: 上半区占比达标 ======
    if da['ratio'] < 0.40 or wa['ratio'] < 0.40 or ma['ratio'] < 0.35:
        return 0, {}

    # ====== 硬条件2: 跌破后能修复 ======
    if da['max_below_days'] > 12 or wa['max_below_days'] > 10 or ma['max_below_days'] > 8:
        return 0, {}

    # ====== 硬条件3: 布林中轨向上 ======
    if da['slope'] <= 0 or wa['slope'] <= 0 or ma['slope'] <= 0:
        return 0, {}

    # ====== 硬条件4: 坡度不过陡 ======
    max_d = 0.03
    max_w = 0.05
    max_m = 0.08

    if da['slope_pct'] > max_d or wa['slope_pct'] > max_w or ma['slope_pct'] > max_m:
        return 0, {}

    # ====== 硬条件5: 无极端涨跌 ======
    extreme_days = 0
    lookback_days = min(len(dk), 30)
    for i in range(-lookback_days, 0):
        k = dk[i]
        if k['open'] > 0:
            chg = (k['close'] - k['open']) / k['open']
            if abs(chg) > 0.07:
                extreme_days += 1

    if extreme_days > 0:
        return 0, {}

    # ====== 综合评分 ======
    d_close = dk[-1]['close']
    w_close = wk[-1]['close']
    m_close = mk[-1]['close']

    # 一底比一底高 (0-36，权重最高)
    asc_score = 0
    if d_asc:
        asc_score += 14
    if w_asc:
        asc_score += 12
    if m_asc:
        asc_score += 10

    # 上半区占比 (0-24)
    def _ratio_score(ana, low_r):
        span = 1.0 - low_r
        return max(0, min(8, (ana['ratio'] - low_r) / span * 8))

    # 趋势质量 (0-12)
    def _slope_quality(sp, mx):
        ideal_low = 0.0003
        ideal_high = mx * 0.5
        if ideal_low <= sp <= ideal_high:
            return 1.0
        if sp < ideal_low:
            return sp / ideal_low
        return max(0, 1 - (sp - ideal_high) / (mx - ideal_high))

    sq = (_slope_quality(da['slope_pct'], max_d)
          + _slope_quality(wa['slope_pct'], max_w)
          + _slope_quality(ma['slope_pct'], max_m)) / 3

    # 当前位置 (0-12)
    def _position_score(close, mid, upper):
        if close < mid:
            return 0
        if close >= upper:
            return 4
        band = upper - mid
        if band <= 0:
            return 2
        return round((close - mid) / band * 4, 1)

    # 修复加分 (0-6)
    recovery_bonus = (2 if da['recovering'] else 0
                      + (2 if wa['recovering'] else 0)
                      + (2 if ma['recovering'] else 0))

    score = round(
          asc_score                                                              # 0-36
        + _ratio_score(da, 0.30) + _ratio_score(wa, 0.30) + _ratio_score(ma, 0.25)  # 0-24
        + sq * 12                                                                # 0-12
        + (_position_score(d_close, da['mid'], da['upper'])
           + _position_score(w_close, wa['mid'], wa['upper'])
           + _position_score(m_close, ma['mid'], ma['upper']))                   # 0-12
        + recovery_bonus                                                          # 0-6
        + 10,                                                                     # 底分
        1,
    )

    score = min(score, 100)

    detail = {
        'd_upper_ratio': round(da['ratio'] * 100, 1),
        'w_upper_ratio': round(wa['ratio'] * 100, 1),
        'm_upper_ratio': round(ma['ratio'] * 100, 1),
        'd_max_below': da['max_below_days'],
        'w_max_below': wa['max_below_days'],
        'm_max_below': ma['max_below_days'],
        'd_recovering': da['recovering'],
        'w_recovering': wa['recovering'],
        'm_recovering': ma['recovering'],
        'd_ascending_lows': d_asc,
        'w_ascending_lows': w_asc,
        'm_ascending_lows': m_asc,
        'd_lows': [round(v, 2) for v in d_lows],
        'w_lows': [round(v, 2) for v in w_lows],
        'm_lows': [round(v, 2) for v in m_lows] if m_lows else [],
        'bb_daily_upper': round(da['upper'], 2),
        'bb_daily_mid': round(da['mid'], 2),
        'bb_weekly_upper': round(wa['upper'], 2),
        'bb_weekly_mid': round(wa['mid'], 2),
        'bb_monthly_upper': round(ma['upper'], 2),
        'bb_monthly_mid': round(ma['mid'], 2),
        'slope_d_pct': round(da['slope_pct'] * 100, 3),
        'slope_w_pct': round(wa['slope_pct'] * 100, 3),
        'slope_m_pct': round(ma['slope_pct'] * 100, 3),
        'extreme_days_30': extreme_days,
        'd_close': round(d_close, 2),
        'w_close': round(w_close, 2),
        'm_close': round(m_close, 2),
    }

    return score, detail
