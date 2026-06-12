"""三上悠亚选股策略 — 日K/周K/月K布林中上轨共振

核心思路：多周期共振，股价在日、周、月三个级别的布林带中长期运行在中轨到上轨之间，
          布林带趋势向上且倾斜温和，近期无极端涨跌，即使短期跌破中轨也能快速修复。

筛选条件：
  1. 三周期最新收盘价均 >= 中轨（跌破中轨后快速修复也算通过）
  2. 三周期「中上轨占比」>= 55%（近20根K线中收在中轨上方的比例），快速修复时可放宽至 45%
  3. 三周期布林中轨向上倾斜，斜率不过陡
  4. 近 30 个交易日无单日涨跌幅 > 7% 的极端行情
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
    """计算布林带（MA20 ± 2*σ）"""
    closes = [k['close'] for k in klines[-period:]]
    ma = sum(closes) / period
    var = sum((c - ma) ** 2 for c in closes) / period
    std = var ** 0.5
    upper = ma + 2 * std
    mid = ma
    lower = ma - 2 * std
    width_pct = (upper - lower) / mid if mid > 0 else 0
    return {'upper': upper, 'mid': mid, 'lower': lower, 'width_pct': width_pct}


def _upper_half_analysis(klines, bb_period=20):
    """分析布林上半区运行情况

    Returns:
        ratio:      最近 bb_period 根K线中收盘 >= 中轨的比例
        recovering: 是否处于快速修复中（近期跌破中轨但已回升至中轨上方）
        mid:        布林中轨
        upper:      布林上轨
    """
    closes = [k['close'] for k in klines[-bb_period:]]
    bb = _calc_bb(klines, bb_period)
    mid = bb['mid']
    upper = bb['upper']

    in_upper = sum(1 for c in closes if c >= mid)
    ratio = in_upper / len(closes)

    # 快速修复检测：看最近 5 根 K 线中是否有跌破再回升的
    recent_check = min(5, len(closes))
    recent = closes[-recent_check:]
    was_below = any(c < mid for c in recent[:-1])
    now_above = closes[-1] >= mid
    recovering = was_below and now_above

    return ratio, recovering, mid, upper


def calc(daily_klines, weekly_klines=None, monthly_klines=None, lookback=60):
    """三上悠亚策略主函数"""
    dk = daily_klines
    wk = weekly_klines or []
    mk = monthly_klines or []

    if len(dk) < 20 or len(wk) < 20 or len(mk) < 20:
        return 0, {}

    # ====== 各周期上半区分析 ======
    d_ratio, d_recovering, d_mid, d_upper = _upper_half_analysis(dk)
    w_ratio, w_recovering, w_mid, w_upper = _upper_half_analysis(wk)
    m_ratio, m_recovering, m_mid, m_upper = _upper_half_analysis(mk)

    # ====== 条件1: 三周期均运行在中上轨 ======
    # 正常达标：中上轨占比 >= 55%
    # 快速修复：允许放宽到 45%，但必须确实在修复中
    def _pass(ratio, recovering):
        if ratio >= 0.55:
            return True
        if recovering and ratio >= 0.45:
            return True
        return False

    if not (_pass(d_ratio, d_recovering) and _pass(w_ratio, w_recovering) and _pass(m_ratio, m_recovering)):
        return 0, {}

    # 最新收盘价至少 >= 中轨（不允许三周期都在中轨下方）
    d_close = dk[-1]['close']
    w_close = wk[-1]['close']
    m_close = mk[-1]['close']

    above_mid_count = sum([d_close >= d_mid, w_close >= w_mid, m_close >= m_mid])
    if above_mid_count == 0:
        return 0, {}

    # ====== 条件2: 布林中轨向上倾斜 ======
    slope_d = _lr_slope([k['close'] for k in dk[-20:]])
    slope_w = _lr_slope([k['close'] for k in wk[-20:]])
    slope_m = _lr_slope([k['close'] for k in mk[-20:]])

    if slope_d <= 0 or slope_w <= 0 or slope_m <= 0:
        return 0, {}

    bb_daily = _calc_bb(dk)
    bb_weekly = _calc_bb(wk)
    bb_monthly = _calc_bb(mk)

    # ====== 条件3: 斜率不过陡 ======
    slope_pct_d = slope_d / bb_daily['mid']
    slope_pct_w = slope_w / bb_weekly['mid']
    slope_pct_m = slope_m / bb_monthly['mid']

    max_d = 0.03
    max_w = 0.05
    max_m = 0.08

    if slope_pct_d > max_d or slope_pct_w > max_w or slope_pct_m > max_m:
        return 0, {}

    # ====== 条件4: 近30个交易日无极端涨跌 ======
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
    # 上半区占比质量（越高越稳定，占分 50）
    def _ratio_score(ratio, recovering):
        base = (ratio - 0.4) / 0.6 * 15  # 0.4->0, 1.0->15
        base = max(0, min(15, base))
        if recovering:
            base *= 0.8  # 修复中的略打折扣
        return base

    r_score_d = _ratio_score(d_ratio, d_recovering)
    r_score_w = _ratio_score(w_ratio, w_recovering)
    r_score_m = _ratio_score(m_ratio, m_recovering)

    # 修复信号加分（占分 6）：快速修复是强势信号
    recovery_bonus = 0
    if d_recovering:
        recovery_bonus += 2
    if w_recovering:
        recovery_bonus += 2
    if m_recovering:
        recovery_bonus += 2

    # 当前价格位置打分（占分 24）：在上半区的哪
    def _position_score(close, mid, upper):
        if close < mid:
            return 0
        if close >= upper:
            return 8
        band = upper - mid
        if band <= 0:
            return 4
        return round((close - mid) / band * 8, 1)

    pos_d = _position_score(d_close, d_mid, d_upper)
    pos_w = _position_score(w_close, w_mid, w_upper)
    pos_m = _position_score(m_close, m_mid, m_upper)

    # 斜率质量（占分 15）
    def _slope_quality(slope_pct, max_pct):
        low = 0.0005
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
          r_score_d + r_score_w + r_score_m     # 上半区稳定性 0-45
        + recovery_bonus                          # 修复加分 0-6
        + pos_d + pos_w + pos_m                   # 当前位置 0-24
        + (sq_d + sq_w + sq_m) / 3 * 15           # 斜率质量 0-15
        + 10,                                      # 硬条件底分
        1,
    )

    score = min(score, 100)

    detail = {
        'd_upper_ratio': round(d_ratio * 100, 1),
        'w_upper_ratio': round(w_ratio * 100, 1),
        'm_upper_ratio': round(m_ratio * 100, 1),
        'd_recovering': d_recovering,
        'w_recovering': w_recovering,
        'm_recovering': m_recovering,
        'bb_daily_upper': round(bb_daily['upper'], 2),
        'bb_daily_mid': round(bb_daily['mid'], 2),
        'bb_daily_lower': round(bb_daily['lower'], 2),
        'bb_weekly_upper': round(bb_weekly['upper'], 2),
        'bb_weekly_mid': round(bb_weekly['mid'], 2),
        'bb_weekly_lower': round(bb_weekly['lower'], 2),
        'bb_monthly_upper': round(bb_monthly['upper'], 2),
        'bb_monthly_mid': round(bb_monthly['mid'], 2),
        'bb_monthly_lower': round(bb_monthly['lower'], 2),
        'd_above_mid': d_close >= d_mid,
        'w_above_mid': w_close >= w_mid,
        'm_above_mid': m_close >= m_mid,
        'slope_d_pct': round(slope_pct_d * 100, 3),
        'slope_w_pct': round(slope_pct_w * 100, 3),
        'slope_m_pct': round(slope_pct_m * 100, 3),
        'extreme_days_30': extreme_days,
        'd_close': round(d_close, 2),
        'w_close': round(w_close, 2),
        'm_close': round(m_close, 2),
    }

    return score, detail
