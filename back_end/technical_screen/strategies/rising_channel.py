"""上升通道选股策略 — 日K/周K/月K布林中上轨共振

核心思路（参考 600900 2023-06 ~ 2024-07）：
  股价突破布林中轨后稳定运行在中轨到上轨之间，布林中轨温和向上倾斜，
  盘中回踩不破前低（一底比一底高），跌破中轨后能快速修复，无极端涨跌。

硬条件：
  1. 三周期波谷低点一底比一底高（至少 2 个周期，这是核心特征）
  2. 三周期布林中轨向上倾斜，坡度不过陡（对中轨序列做线性回归），至少 2 个周期满足
  3. 三周期大部分时间在中上轨（日 >= 40%，周 >= 40%，月 >= 35%），至少 2 个周期满足
  4. 跌破中轨后能在合理时间内修复（日 <= 12天，周 <= 10周，月 <= 8月），至少 2 个周期满足
  5. 无跌停等极端下跌行情（单日跌幅 > 9.5% 视为极端，上涨方向不限制）
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


def _calc_rolling_mids(klines, bb_period=20):
    """计算每根K线对应时刻的布林中轨（滚动MA），返回与klines等长的中轨序列。
    前 bb_period-1 根无法计算中轨，填充为 None。
    """
    closes = [k['close'] for k in klines]
    n = len(closes)
    mids = [None] * (bb_period - 1)
    for i in range(bb_period - 1, n):
        window = closes[i - bb_period + 1:i + 1]
        mids.append(sum(window) / bb_period)
    return mids


def _find_valley_lows(klines, min_valley_count=3):
    """检测波谷低点（局部最低），判断是否一底比一底高

    滑动窗口找局部最低点：当前收盘价 < 左右各 lookback 根内的最低价。
    min_valley_count: 至少需要多少个波谷才能判断趋势。
    """
    n = len(klines)
    closes = [k['close'] for k in klines]
    lookback = max(2, n // 15)

    valleys = []
    for i in range(lookback, n - lookback):
        left_min = min(closes[i - lookback:i])
        right_min = min(closes[i + 1:i + 1 + lookback])
        if closes[i] <= left_min and closes[i] <= right_min:
            # 合并相近的波谷（10根以内取最低的）
            if valleys and i - valleys[-1][0] < lookback * 2:
                if closes[i] < valleys[-1][1]:
                    valleys[-1] = (i, closes[i])
            else:
                valleys.append((i, closes[i]))

    if len(valleys) < min_valley_count:
        return False, [v[1] for v in valleys]

    low_values = [v[1] for v in valleys]
    ascending = True
    for i in range(1, len(low_values)):
        if low_values[i] < low_values[i - 1] * 0.995:
            ascending = False
            break
    return ascending, [round(v, 2) for v in low_values]


def _calc_mid_slope(klines, bb_period=20, mid_window=20):
    """对布林中轨序列做线性回归，计算中轨斜率。

    在 klines 上滑动计算每个窗口的中轨值，得到中轨序列，再做线性回归。
    """
    closes = [k['close'] for k in klines]
    n = len(closes)

    mids = []
    for i in range(bb_period - 1, n):
        window = closes[i - bb_period + 1:i + 1]
        mids.append(sum(window) / bb_period)

    if len(mids) < mid_window:
        mids = mids[-mid_window:] if mids else []

    if len(mids) < 5:
        return 0, 0

    mid_series = mids[-mid_window:]
    slope = _lr_slope(mid_series)
    avg_mid = sum(mid_series) / len(mid_series)
    slope_pct = slope / avg_mid if avg_mid > 0 else 0
    return slope, slope_pct


def _upper_half_analysis(klines, bb_period=20, ratio_period=20):
    """分析布林带上半区特征，使用滚动中轨做动态判断。"""
    closes_all = [k['close'] for k in klines]
    bb = _calc_bb(klines, bb_period)
    mid_latest = bb['mid']
    upper = bb['upper']

    # 使用滚动中轨计算上半区占比（每个时间点用各自的中轨）
    rolling_mids = _calc_rolling_mids(klines, bb_period)
    recent_closes = closes_all[-ratio_period:]
    recent_mids = rolling_mids[-ratio_period:]
    in_upper = sum(1 for c, m in zip(recent_closes, recent_mids) if m is not None and c >= m)
    valid_count = sum(1 for m in recent_mids if m is not None)
    ratio = in_upper / valid_count if valid_count > 0 else 0

    # 使用滚动中轨统计更长时间内的连续跌破
    below_window = closes_all[-max(ratio_period * 2, 40):]
    below_mids = rolling_mids[-max(ratio_period * 2, 40):]
    max_consecutive_below = 0
    current_streak = 0
    for c, m in zip(below_window, below_mids):
        if m is not None and c < m:
            current_streak += 1
            max_consecutive_below = max(max_consecutive_below, current_streak)
        else:
            current_streak = 0

    # 修复检测
    recent5_closes = closes_all[-5:]
    recent5_mids = rolling_mids[-5:]
    was_below = any(
        m is not None and c < m
        for c, m in zip(recent5_closes[:-1], recent5_mids[:-1])
    )
    now_above = (
        recent5_mids[-1] is not None and recent5_closes[-1] >= recent5_mids[-1]
    )
    recovering = was_below and now_above

    # 对中轨序列做线性回归，而非收盘价
    slope, slope_pct = _calc_mid_slope(klines, bb_period, mid_window=20)

    return {
        'ratio': ratio,
        'max_below_days': max_consecutive_below,
        'recovering': recovering,
        'mid': mid_latest,
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

    # ====== 硬条件0: 一底比一底高（波谷检测，核心特征，至少 2 个周期） ======
    d_asc, d_lows = _find_valley_lows(dk[-120:], min_valley_count=3)
    w_asc, w_lows = _find_valley_lows(wk, min_valley_count=3)
    m_asc, m_lows = _find_valley_lows(mk[-24:], min_valley_count=2)

    asc_count = sum([d_asc, w_asc, m_asc])
    if asc_count < 2:
        return 0, {}

    # ====== 硬条件1: 上半区占比达标（至少 2 个周期） ======
    ratio_ok = (
        (1 if da['ratio'] >= 0.40 else 0)
        + (1 if wa['ratio'] >= 0.40 else 0)
        + (1 if ma['ratio'] >= 0.35 else 0)
    )
    if ratio_ok < 2:
        return 0, {}

    # ====== 硬条件2: 跌破后能修复（至少 2 个周期） ======
    repair_ok = (
        (1 if da['max_below_days'] <= 12 else 0)
        + (1 if wa['max_below_days'] <= 10 else 0)
        + (1 if ma['max_below_days'] <= 8 else 0)
    )
    if repair_ok < 2:
        return 0, {}

    # ====== 硬条件3: 布林中轨向上（至少 2 个周期） ======
    slope_up_ok = (
        (1 if da['slope'] > 0 else 0)
        + (1 if wa['slope'] > 0 else 0)
        + (1 if ma['slope'] > 0 else 0)
    )
    if slope_up_ok < 2:
        return 0, {}

    # ====== 硬条件4: 坡度不过陡（至少 2 个周期） ======
    max_d = 0.03
    max_w = 0.05
    max_m = 0.08

    slope_steep_ok = (
        (1 if da['slope_pct'] <= max_d else 0)
        + (1 if wa['slope_pct'] <= max_w else 0)
        + (1 if ma['slope_pct'] <= max_m else 0)
    )
    if slope_steep_ok < 2:
        return 0, {}

    # ====== 硬条件5: 无极端下跌（跌停板附近） ======
    extreme_days = 0
    lookback_days = min(len(dk), 30)
    for i in range(-lookback_days, 0):
        k = dk[i]
        if k['open'] > 0:
            chg = (k['close'] - k['open']) / k['open']
            if chg < -0.095:
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
    # low_r 基准接近硬阈值，避免刚达标的股票被过度惩罚
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
        + _ratio_score(da, 0.38) + _ratio_score(wa, 0.38) + _ratio_score(ma, 0.33)  # 0-24
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
        'd_lows': d_lows,
        'w_lows': w_lows,
        'm_lows': m_lows,
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
