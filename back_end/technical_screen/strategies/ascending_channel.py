"""上升通道选股策略 — 基于线性回归检测上升通道"""


def calc(klines, lookback=60):
    """上升通道检测

    对最近 lookback 根 K 线的最高价和最低价分别做线性回归，
    判断股票是否处于上升通道中，返回评分和通道详情。
    """
    if len(klines) < lookback:
        return 0, {}

    window = klines[-lookback:]
    highs = [k['high'] for k in window]
    lows = [k['low'] for k in window]
    closes = [k['close'] for k in window]
    volumes = [k['volume'] for k in window]

    def _lr(y):
        n = len(y)
        x = list(range(n))
        sx = sum(x)
        sy = sum(y)
        sxy = sum(x[i] * y[i] for i in range(n))
        sx2 = sum(v ** 2 for v in x)
        d = n * sx2 - sx * sx
        if d == 0:
            return 0, 0, 0
        sl = (n * sxy - sx * sy) / d
        ic = (sy - sl * sx) / n
        ym = sy / n
        ssr = sum((y[i] - (sl * x[i] + ic)) ** 2 for i in range(n))
        sst = sum((v - ym) ** 2 for v in y)
        r2 = 1 - ssr / sst if sst > 0 else 0
        return sl, ic, r2

    hs, hi, hr = _lr(highs)
    ls, li, lr = _lr(lows)

    if hs <= 0 or ls <= 0 or hr < 0.6 or lr < 0.6 or hs > ls * 3:
        return 0, {}
    idx = lookback - 1
    upper = hs * idx + hi
    lower = ls * idx + li
    cur = closes[-1]
    cw = upper - lower
    if cw <= 0 or cw / lower > 0.30:
        return 0, {}
    pos = (cur - lower) / cw
    if pos < 0.2 or pos > 0.9:
        return 0, {}
    v5 = sum(volumes[-5:]) / 5 if len(volumes) >= 5 else 0
    v20 = sum(volumes[-20:]) / 20 if len(volumes) >= 20 else v5
    if v20 > 0 and v5 / v20 < 0.8:
        return 0, {}

    score = round(
        hr * 30
        + lr * 30
        + (1 - abs(pos - 0.5) * 2) * 20
        + min(v5 / v20 * 10, 10 if v20 > 0 else 0)
        + min(hs / (lower / 100) * 5, 10),
        1,
    )
    return score, {
        'upper': round(upper, 2),
        'lower': round(lower, 2),
        'hi_slope': round(hs, 4),
        'lo_slope': round(ls, 4),
        'hi_r2': round(hr, 2),
        'lo_r2': round(lr, 2),
        'pos': round(pos * 100, 1),
        'channel_width_pct': round(cw / lower * 100, 1),
        'vol_ratio': round(v5 / v20, 2) if v20 > 0 else 1,
    }
