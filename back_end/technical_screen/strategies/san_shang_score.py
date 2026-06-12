"""三上评分 — 趋势感知的看涨倾向评分 (0-100)

核心：评分本身代表 0-100 的看涨倾向，而非二分方向+置信度。
      50 分中性，越高越看涨，越低越看跌。
      趋势感知：趋势股基础分偏多，震荡股近中性。

返回:
    {'direction': 'bullish'|'bearish', 'score': 0-100, 'detail': {...}}
"""


def _lr_slope(values):
    n = len(values)
    x = list(range(n))
    sx = sum(x)
    sy = sum(values)
    sxy = sum(x[i] * values[i] for i in range(n))
    sx2 = sum(v ** 2 for v in x)
    d = n * sx2 - sx * sx
    return (n * sxy - sx * sy) / d if d else 0


def _ascending_lows(klines, segments=4):
    n = len(klines)
    seg_size = n // segments
    if seg_size < 3:
        return False
    lows = []
    for s in range(segments):
        st = s * seg_size
        ed = st + seg_size if s < segments - 1 else n
        lows.append(min(k['close'] for k in klines[st:ed]))
    return all(lows[i] >= lows[i-1] * 0.995 for i in range(1, len(lows)))


def _detect_trend(klines):
    closes = [k['close'] for k in klines]
    if len(klines) < 60:
        return 0, False
    asc = _ascending_lows(klines[-60:], 4)
    recent = closes[-20:]
    ma = sum(recent) / 20
    std = (sum((c - ma)**2 for c in recent) / 20) ** 0.5
    slp = _lr_slope(closes[-20:]) / ma if ma > 0 else 0
    ratio = sum(1 for c in recent if c >= ma) / 20
    in_upper = closes[-1] >= ma
    # 连续强度分 0-3
    strength = sum([asc, slp > 0.0002 and slp < 0.03, in_upper, ratio >= 0.4])
    return strength, strength >= 2


def calc(klines):
    if len(klines) < 20:
        return _empty()

    closes = [k['close'] for k in klines]
    opens = [k['open'] for k in klines]
    highs = [k['high'] for k in klines]
    lows = [k['low'] for k in klines]
    volumes = [k['volume'] for k in klines]

    k = klines[-1]
    co, cc, ch, cl, cv = k['open'], k['close'], k['high'], k['low'], k['volume']

    def _ma(d, p):
        return sum(d[-p:]) / p if len(d) >= p else None

    trend_str, is_trend = _detect_trend(klines)

    # ---- 基础指标 ----
    ma5 = _ma(closes, 5)
    ma10 = _ma(closes, 10)
    ma20 = _ma(closes, 20)
    avg_v5 = _ma(volumes, 5) or cv
    avg_v20 = _ma(volumes, 20) or avg_v5

    chg_1d = (closes[-1] - closes[-2]) / closes[-2] if len(closes) > 1 and closes[-2] else 0
    chg_3d = (closes[-1] - closes[-4]) / closes[-4] if len(closes) > 3 and closes[-4] else 0
    chg_5d = (closes[-1] - closes[-6]) / closes[-6] if len(closes) > 5 and closes[-6] else 0
    today_up = cc >= co
    body_pct = (cc - co) / co if co > 0 else 0

    rng = ch - cl
    close_pos = (cc - cl) / rng if rng > 0 else 0.5

    gap = (co - closes[-2]) / closes[-2] if len(closes) > 1 and closes[-2] > 0 else 0
    v_ratio = cv / avg_v5 if avg_v5 > 0 else 1
    v_trend = avg_v5 / avg_v20 if avg_v20 and avg_v20 > 0 else 1
    ma20_dist = (cc - ma20) / ma20 if ma20 and ma20 > 0 else 0

    cons_up = cons_dn = 0
    for i in range(-1, -min(len(closes), 10) - 1, -1):
        if closes[i] >= opens[i] and cons_dn == 0:
            cons_up += 1
        elif closes[i] < opens[i] and cons_up == 0:
            cons_dn += 1
        else:
            break

    h60 = max(highs[-60:]) if len(highs) >= 60 else max(highs)
    l60 = min(lows[-60:]) if len(lows) >= 60 else min(lows)
    pos60 = (cc - l60) / (h60 - l60) if h60 > l60 else 0.5

    trs = [max(highs[i]-lows[i], abs(highs[i]-(closes[i-1] if i-1 >= -len(closes) else closes[i])),
               abs(lows[i]-(closes[i-1] if i-1 >= -len(closes) else closes[i])))
           for i in range(-14, 0)]
    atr_pct = (sum(trs) / len(trs)) / cc if trs and cc > 0 else 0.01

    # ============================================================
    # 直接算看涨倾向分 (0-100, 50=中性)
    # ============================================================
    score = 50  # 起始中性

    # --- 短期动量 (最强信号) ---
    # 3日动量
    if chg_3d > 0.015:
        score += 10
    elif chg_3d > 0.005:
        score += 6
    elif chg_3d > 0:
        score += 2
    elif chg_3d < -0.03:
        score -= 12
    elif chg_3d < -0.01:
        score -= 6
    elif chg_3d < 0:
        score -= 3

    # 1日动量
    if 0.008 < chg_1d <= 0.025:
        score += 8
    elif 0 < chg_1d <= 0.008:
        score += 4
    elif chg_1d > 0.04:
        score -= 3
    elif -0.025 < chg_1d <= 0:
        score -= 5
    elif chg_1d <= -0.025:
        score -= 9

    # 日内强度
    if close_pos > 0.75 and today_up:
        score += 5
    elif close_pos > 0.55 and today_up:
        score += 3
    elif close_pos < 0.30 and not today_up:
        score -= 5
    elif close_pos < 0.45 and not today_up:
        score -= 3
    elif close_pos > 0.65 and not today_up:
        score += 3
    elif close_pos < 0.35 and today_up:
        score -= 3

    # 3日方向一致
    chgs3 = [(closes[-1]-closes[-2])/closes[-2], (closes[-2]-closes[-3])/closes[-3],
             (closes[-3]-closes[-4])/closes[-4]]
    up_cnt = sum(1 for c in chgs3 if c > 0 and abs(c) < 100)
    if up_cnt == 3:
        score += 8
    elif up_cnt == 2:
        score += 5
    elif up_cnt == 0:
        score -= 8
    else:
        score -= 2

    # 连阳/连阴
    if cons_up >= 5:
        score -= 3
    if cons_dn >= 5:
        score += 4
    elif cons_dn >= 3:
        score -= 4

    # 缺口
    if gap > 0.015:
        score += 5 if today_up else -5
    elif gap < -0.015:
        score += 5 if today_up else -6

    # MA20偏离
    if ma20_dist > 0.15:
        score -= is_trend and 2 or 6
    elif ma20_dist > 0.10:
        score -= is_trend and 0 or 3
    elif ma20_dist < -0.10:
        score += 3 if today_up else -2

    # --- 量价确认 ---
    if today_up and v_ratio > 1.15:
        score += 8
    elif today_up and v_ratio > 0.85:
        score += 2
    elif today_up and v_ratio < 0.65:
        score -= 5
    elif not today_up and v_ratio < 0.75:
        score += 5
    elif not today_up and 0.85 <= v_ratio <= 1.10:
        score -= 7
    elif not today_up and v_ratio > 1.25:
        score -= 7 if chg_1d > -0.03 else 5

    if v_trend > 1.05:
        score += 2 if today_up else -3
    elif v_trend < 0.75:
        score -= 2

    if v_ratio > 1.3 and abs(chg_1d) < 0.015:
        score += -7 if today_up else 5

    # --- 趋势对齐 ---
    if is_trend:
        score += 6 + trend_str * 2  # 趋势基础加分
        # 趋势+收阳 vs 趋势+收阴
        if today_up:
            score += 4
        elif pos60 > 0.30:
            score += 0  # 趋势中阴线也正常
        # 趋势位置
        if pos60 >= 0.50:
            score += 4
        elif pos60 >= 0.25:
            score += 2
        else:
            score -= 2
    else:
        # 非趋势：均值回归位置
        if 0.10 <= pos60 <= 0.35:
            score += 6
        elif 0.35 < pos60 <= 0.55:
            score += 3
        elif pos60 > 0.80:
            score -= 3
        elif pos60 < 0.05:
            score -= 5

    # --- K线形态 ---
    body = abs(cc - co)
    body_pct2 = body / co if co > 0 else 0
    us = ch - max(cc, co)
    ls = min(cc, co) - cl

    if ls > body * 2 and us < body * 0.5 and body_pct2 > 0:
        score += 5 if pos60 < 0.4 else 2
    if body_pct2 < 0.0015 and (ch - cl) / co > 0.01:
        score += 2
    if us > body * 2 and ls < body * 0.5 and pos60 > 0.75 and not is_trend:
        score -= 5
    if today_up and us < body * 0.2 and 0.005 <= body_pct2 <= 0.04:
        score += 4
    if not today_up and ls < body * 0.2:
        score -= 4
    if len(klines) > 1:
        prev = klines[-2]
        if today_up and prev['close'] < prev['open'] and body > abs(prev['close'] - prev['open']):
            score += 4

    # ---趋势偏置（MA空头压制）---
    chg_20d = (closes[-1] - closes[-20]) / closes[-20] if len(closes) > 19 and closes[-20] else 0
    if ma5 and ma10 and ma20 and chg_20d < -0.03:
        if cc < ma5 < ma10 < ma20:
            score -= is_trend and 3 or 7
        elif cc < ma5 < ma10:
            score -= 3
    if chg_20d < -0.12:
        score -= 8
    elif chg_20d < -0.06:
        score -= 4

    # 最终 clip + 方向判定
    score = max(1, min(99, round(score)))

    if score >= 55:
        direction = 'bullish'
    elif score <= 45:
        direction = 'bearish'
    else:
        # 45-55: 中性区间，趋势股偏多
        direction = 'bullish' if is_trend else ('bullish' if score >= 50 else 'bearish')

    return {
        'direction': direction,
        'score': score,
        'detail': {
            'is_trending': is_trend,
            'trend_strength': trend_str,
            'chg_5d': round(chg_5d * 100, 2),
            'chg_1d': round(chg_1d * 100, 2),
            'pos_60': round(pos60 * 100, 1),
            'vol_ratio': round(v_ratio, 2),
            'vol_trend': round(v_trend, 2),
            'atr_pct': round(atr_pct * 100, 2),
            'gap_pct': round(gap * 100, 2),
            'close_pos': round(close_pos * 100, 1),
            'consecutive_up': cons_up,
            'consecutive_down': cons_dn,
            'ma20_dist': round(ma20_dist * 100, 2),
            'today_up': today_up,
        },
    }


def _empty():
    return {'direction': 'bullish', 'score': 0, 'detail': {}}
