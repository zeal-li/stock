"""三上悠亚选股策略 — 日K/周K/月K共振布林上轨

核心思路：多周期共振，股价在日、周、月三个级别都紧贴布林上轨运行，
          布林带整体趋势向上且倾斜温和，近期无极端涨跌，适合趋势跟随。

筛选条件：
  1. 日K/周K/月K 收盘价均在布林上轨附近（>= MA20 + 1.8 * STD，即上轨区间内）
  2. 三个周期的布林中轨（MA20）均向上倾斜，趋势确认
  3. 布林中轨斜率不能过陡（日线 < 3%/天，周线 < 5%/周，月线 < 8%/月）
  4. 近 30 个交易日无单日涨跌幅超过 ±7% 的极端行情
"""


def _lr_slope(values):
    """对 values 做线性回归，返回斜率"""
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
    """计算布林带：返回 {upper, mid, lower, width_pct}"""
    closes = [k['close'] for k in klines[-period:]]
    ma = sum(closes) / period
    var = sum((c - ma) ** 2 for c in closes) / period
    std = var ** 0.5
    upper = ma + 2 * std
    mid = ma
    lower = ma - 2 * std
    width_pct = (upper - lower) / mid if mid > 0 else 0
    return {'upper': upper, 'mid': mid, 'lower': lower, 'width_pct': width_pct}


def _at_upper_zone(close, bb):
    """收盘价是否在布林上轨区间（上轨附近，包含轻微站上和贴近）"""
    # 上轨区间：从 mid + 1.8*std 到 upper + 0.5*std，即上轨上下各留一点容差
    upper = bb['upper']
    mid = bb['mid']
    std_est = (upper - mid) / 2
    zone_low = mid + 1.8 * std_est
    zone_high = upper + 0.5 * std_est
    return zone_low <= close <= zone_high


def calc(daily_klines, weekly_klines=None, monthly_klines=None, lookback=60):
    """三上悠亚策略主函数

    Args:
        daily_klines: 日K线列表
        weekly_klines: 周K线列表（由 _scan_one 传入）
        monthly_klines: 月K线列表（由 _scan_one 传入）

    Returns:
        (score, detail) — score=0 表示不满足条件
    """
    dk = daily_klines
    wk = weekly_klines or []
    mk = monthly_klines or []

    # 布林带至少需要 20 根 K 线
    if len(dk) < 20 or len(wk) < 20 or len(mk) < 20:
        return 0, {}

    # ====== 计算各周期布林带 ======
    bb_daily = _calc_bb(dk)
    bb_weekly = _calc_bb(wk)
    bb_monthly = _calc_bb(mk)

    d_close = dk[-1]['close']
    w_close = wk[-1]['close']
    m_close = mk[-1]['close']

    # ====== 条件1: 三个周期均在布林上轨区间 ======
    d_at_upper = _at_upper_zone(d_close, bb_daily)
    w_at_upper = _at_upper_zone(w_close, bb_weekly)
    m_at_upper = _at_upper_zone(m_close, bb_monthly)

    if not (d_at_upper and w_at_upper and m_at_upper):
        return 0, {}

    # ====== 条件2: 布林中轨向上倾斜（用最近20根K线收盘价的线性回归斜率） ======
    slope_d = _lr_slope([k['close'] for k in dk[-20:]])
    slope_w = _lr_slope([k['close'] for k in wk[-20:]])
    slope_m = _lr_slope([k['close'] for k in mk[-20:]])

    if slope_d <= 0 or slope_w <= 0 or slope_m <= 0:
        return 0, {}

    # ====== 条件3: 斜率不能过陡 ======
    slope_pct_d = slope_d / bb_daily['mid']  # 日线每根K线的斜率百分比
    slope_pct_w = slope_w / bb_weekly['mid']
    slope_pct_m = slope_m / bb_monthly['mid']

    max_d = 0.03   # 日线斜率不超过 3%/天
    max_w = 0.05   # 周线斜率不超过 5%/周
    max_m = 0.08   # 月线斜率不超过 8%/月

    if slope_pct_d > max_d or slope_pct_w > max_w or slope_pct_m > max_m:
        return 0, {}

    # ====== 条件4: 近30个交易日无极端涨跌（单日涨跌幅 > 7%） ======
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
    # 上轨贴合度：计算收盘价在上轨区间的归一化位置（1 = 恰好在上轨线上，最优）
    def _proximity(close, bb):
        upper = bb['upper']
        mid = bb['mid']
        std_est = (upper - mid) / 2
        zone_low = mid + 1.8 * std_est
        zone_high = upper + 0.5 * std_est
        if zone_high == zone_low:
            return 0
        # 归一化到 [0, 1]，越靠近上轨线越接近 1
        raw = (close - zone_low) / (zone_high - zone_low)
        # 理想位置是上轨线（upper），对应 raw ≈ (upper - zone_low) / (zone_high - zone_low)
        ideal_raw = (upper - zone_low) / (zone_high - zone_low)
        # 距离理想位置越近越好
        return 1 - abs(raw - ideal_raw)

    prox_d = _proximity(d_close, bb_daily)
    prox_w = _proximity(w_close, bb_weekly)
    prox_m = _proximity(m_close, bb_monthly)

    # 斜率质量：在 [0.05%, max] 范围内越居中越好
    def _slope_quality(slope_pct, max_pct):
        # 理想斜率范围：0.001 ~ max_pct*0.6 (温和爬升)
        low = 0.001
        high = max_pct * 0.6
        if low <= slope_pct <= high:
            return 1.0
        if slope_pct < low:
            return slope_pct / low
        return max(0, 1 - (slope_pct - high) / (max_pct - high))

    sq_d = _slope_quality(slope_pct_d, max_d)
    sq_w = _slope_quality(slope_pct_w, max_w)
    sq_m = _slope_quality(slope_pct_m, max_m)

    score = round(
          prox_d * 22
        + prox_w * 22
        + prox_m * 22
        + (sq_d + sq_w + sq_m) / 3 * 15  # 斜率质量
        + 19,  # 通过全部硬条件的底分
        1,
    )

    score = min(score, 100)

    detail = {
        'bb_daily_upper': round(bb_daily['upper'], 2),
        'bb_daily_mid': round(bb_daily['mid'], 2),
        'bb_daily_lower': round(bb_daily['lower'], 2),
        'bb_weekly_upper': round(bb_weekly['upper'], 2),
        'bb_weekly_mid': round(bb_weekly['mid'], 2),
        'bb_weekly_lower': round(bb_weekly['lower'], 2),
        'bb_monthly_upper': round(bb_monthly['upper'], 2),
        'bb_monthly_mid': round(bb_monthly['mid'], 2),
        'bb_monthly_lower': round(bb_monthly['lower'], 2),
        'd_at_upper': d_at_upper,
        'w_at_upper': w_at_upper,
        'm_at_upper': m_at_upper,
        'slope_d_pct': round(slope_pct_d * 100, 3),
        'slope_w_pct': round(slope_pct_w * 100, 3),
        'slope_m_pct': round(slope_pct_m * 100, 3),
        'extreme_days_30': extreme_days,
        'd_close': round(d_close, 2),
        'w_close': round(w_close, 2),
        'm_close': round(m_close, 2),
    }

    return score, detail
