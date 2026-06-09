"""明日涨跌预测评分 — 基于K线最新涨跌幅度、量价关系、高低位置多因子评分

不会作为独立策略出现在策略选择器中，而是在其他策略筛选完成后，
自动对筛选结果计算预测评分。

返回格式:
    {
        'direction': 'bullish' | 'bearish',
        'score': 0-100  置信度
        'detail': {...} 各因子明细
    }
"""


def calc(klines):
    """基于K线多因子模型预测明日涨跌方向及置信度

    四大因子（满分 100）：
    1. 短期动量 (35) — 近5日价格走势与今日涨跌
    2. 量价关系 (30) — 量能配合程度
    3. 位置高低 (20) — 60日波动区间内的相对位置
    4. K线形态 (15) — 单根K线/组合形态信号
    """
    if len(klines) < 20:
        return _empty()

    closes = [k['close'] for k in klines]
    opens = [k['open'] for k in klines]
    highs = [k['high'] for k in klines]
    lows = [k['low'] for k in klines]
    volumes = [k['volume'] for k in klines]

    latest = klines[-1]
    cur_open = latest['open']
    cur_close = latest['close']
    cur_high = latest['high']
    cur_low = latest['low']
    cur_vol = latest['volume']

    # ---------- 辅助函数 ----------
    def _ma(data, period):
        if len(data) < period:
            return None
        return sum(data[-period:]) / period

    # ---------- 1. 短期动量 (35分) ----------
    momentum_score = 0

    # 近5日涨跌幅
    chg_1d = (closes[-1] - closes[-2]) / closes[-2] if len(closes) >= 2 else 0
    chg_5d = (closes[-1] - closes[-6]) / closes[-6] if len(closes) >= 6 else 0
    chg_3d = (closes[-1] - closes[-4]) / closes[-4] if len(closes) >= 4 else 0

    # 今日涨跌（收阳 vs 收阴）
    today_up = cur_close >= cur_open
    today_body_pct = (cur_close - cur_open) / cur_open if cur_open > 0 else 0

    if 0.005 < chg_5d <= 0.04:       # 温和上涨 0.5%-4%
        momentum_score += 15
    elif 0.002 < chg_5d <= 0.005:     # 微涨
        momentum_score += 10
    elif -0.01 < chg_5d <= 0.002:     # 横盘微涨
        momentum_score += 6

    if chg_1d > 0:
        if 0.01 < chg_1d <= 0.03:     # 今日涨1-3%，动能健康
            momentum_score += 10
        elif 0 < chg_1d <= 0.01:       # 小涨
            momentum_score += 6
        elif chg_1d > 0.05:            # 涨幅过大，统计上易回调
            momentum_score += 2
    elif chg_1d < -0.04:               # 今日大跌
        momentum_score -= 8
    elif chg_1d < 0:
        momentum_score -= 3

    # 3日趋势方向一致性
    chg_1 = (closes[-1] - closes[-2]) / closes[-2] if len(closes) >= 2 else 0
    chg_2 = (closes[-2] - closes[-3]) / closes[-3] if len(closes) >= 3 else 0
    chg_3 = (closes[-3] - closes[-4]) / closes[-4] if len(closes) >= 4 else 0
    up_days = sum(1 for c in [chg_1, chg_2, chg_3] if c > 0)
    if up_days >= 2:
        momentum_score += 10
    elif up_days == 0:
        momentum_score -= 5

    momentum_score = max(0, min(35, momentum_score))

    # ---------- 2. 量价关系 (30分) ----------
    vol_score = 15  # 默认基础分

    avg_vol_5 = _ma(volumes, 5) or cur_vol
    avg_vol_20 = _ma(volumes, 20) or avg_vol_5
    vol_ratio_today = cur_vol / avg_vol_5 if avg_vol_5 > 0 else 1
    vol_ratio_20 = cur_vol / avg_vol_20 if avg_vol_20 > 0 else 1

    # 价升量增（强势信号）
    if today_up and vol_ratio_today > 1.2:
        vol_score += 12
    elif today_up and vol_ratio_today > 1.0:
        vol_score += 6
    # 价跌量缩（止跌信号）
    elif not today_up and vol_ratio_today < 0.8:
        vol_score += 8
    # 价跌量增（危险信号）
    elif not today_up and vol_ratio_today > 1.3:
        vol_score -= 10
    # 价升量缩（动能衰减）
    elif today_up and vol_ratio_today < 0.7:
        vol_score -= 5

    # 近5日量价同步性：检查上涨日是否放量
    sync_count = 0
    for i in range(-5, 0):
        day_up = closes[i] >= opens[i]
        day_vol_ratio = volumes[i] / avg_vol_20 if avg_vol_20 > 0 else 1
        if day_up and day_vol_ratio > 1.0:
            sync_count += 1
        elif not day_up and day_vol_ratio < 1.0:
            sync_count += 1
    vol_score += min(sync_count, 3) * 1   # 最多 +3

    vol_score = max(0, min(30, vol_score))

    # ---------- 3. 位置高低 (20分) ----------
    h60 = max(highs[-60:]) if len(highs) >= 60 else max(highs)
    l60 = min(lows[-60:]) if len(lows) >= 60 else min(lows)
    pos = (cur_close - l60) / (h60 - l60) if h60 > l60 else 0.5

    position_score = 0
    if 0.15 <= pos <= 0.35:        # 低位区域，反弹空间大
        position_score = 18
    elif 0.35 < pos <= 0.55:       # 中低位，安全
        position_score = 15
    elif 0.55 < pos <= 0.75:       # 中高位
        position_score = 8
    elif pos > 0.85:               # 高位，易回调
        position_score = 2
    elif pos < 0.15:               # 极低位，可能弱势
        position_score = 5

    # 均线位置加分项
    ma5 = _ma(closes, 5)
    ma10 = _ma(closes, 10)
    ma20 = _ma(closes, 20)
    if ma5 and ma10 and ma20:
        if cur_close > ma5 > ma10:         # 均线多头
            position_score += 2
        if ma5 and ma20 and cur_close > ma20:   # 在均线上方
            position_score += 0

    position_score = min(20, position_score)

    # ---------- 4. K线形态 (15分) ----------
    pattern_score = 0

    body = abs(cur_close - cur_open)
    body_pct = body / cur_open if cur_open > 0 else 0
    upper_shadow = cur_high - max(cur_close, cur_open)
    lower_shadow = min(cur_close, cur_open) - cur_low
    full_range = cur_high - cur_low
    shadow_ratio = full_range / cur_open if cur_open > 0 and full_range > 0 else 0

    # 锤子线（下影线长，实体小，低位出现 — 反转信号）
    if lower_shadow > body * 2 and upper_shadow < body * 0.5 and body_pct > 0:
        if pos < 0.4:              # 低位锤子线，看涨
            pattern_score += 12
        else:
            pattern_score += 5

    # 十字星/十字线（实体极小）
    if body_pct < 0.002 and shadow_ratio > 0.01:
        pattern_score += 7

    # 射击之星/倒锤子（上影线长，高位）
    if upper_shadow > body * 2 and lower_shadow < body * 0.5:
        if pos > 0.65:
            pattern_score -= 8   # 高位射击之星，看跌

    # 光头阳线（收在最高点附近）
    if today_up and upper_shadow < body * 0.2:
        if 0.01 <= today_body_pct <= 0.04:
            pattern_score += 10
        else:
            pattern_score += 5

    # 光脚阴线（收在最低点附近）
    if not today_up and lower_shadow < body * 0.2:
        pattern_score -= 6

    # 阳包阴（今日阳线实体完全覆盖昨日阴线）
    if len(klines) >= 2:
        prev = klines[-2]
        prev_body = abs(prev['close'] - prev['open'])
        prev_up = prev['close'] >= prev['open']
        if today_up and not prev_up and body > prev_body:
            # 低位阳包阴
            if pos < 0.5:
                pattern_score += 12
            else:
                pattern_score += 6

    pattern_score = max(-8, min(15, pattern_score))

    # ---------- 综合判定 ----------
    # 看涨总分（动量 + 量价 + 位置 + 形态）
    bullish_raw = momentum_score + vol_score + position_score + pattern_score
    bullish_raw = max(0, min(100, bullish_raw))

    # 同时计算看跌方向分数（对位置和形态取反向信号）
    # 位置因子：高位 → 看跌方向
    if pos > 0.75:
        bearish_position = min(15, int((pos - 0.5) * 30))
    elif pos > 0.6:
        bearish_position = 5
    else:
        bearish_position = 0

    # 动量反向：连跌 → 看跌延续风险
    if chg_5d < -0.03:
        bearish_momentum = min(20, int(abs(chg_5d) * 300))
    elif chg_5d < -0.01:
        bearish_momentum = 8
    else:
        bearish_momentum = 0

    # 量价反向：放量下跌
    if not today_up and vol_ratio_today > 1.2:
        bearish_vol = min(15, int(vol_ratio_today * 10))
    elif not today_up and vol_ratio_today > 0.9:
        bearish_vol = 3
    else:
        bearish_vol = 0

    # 形态看跌
    bearish_pattern = abs(min(0, pattern_score)) if pattern_score < 0 else 0

    bearish_raw = bearish_position + bearish_momentum + bearish_vol + bearish_pattern
    bearish_raw = min(100, bearish_raw)

    # 方向判定：比较看涨与看跌信号强度
    # 设置最低阈值，避免模棱两可时给出高分
    if bullish_raw >= bearish_raw + 15:
        direction = 'bullish'
        # 置信度 = 看涨分 + 小幅调整
        confidence = min(100, bullish_raw + max(0, (bullish_raw - bearish_raw) // 3))
    elif bearish_raw >= bullish_raw + 15:
        direction = 'bearish'
        confidence = min(100, bearish_raw + max(0, (bearish_raw - bullish_raw) // 3))
    else:
        # 信号矛盾或不够强，取较弱的那方，置信度降低
        if bullish_raw >= bearish_raw:
            direction = 'bullish'
            confidence = max(10, bullish_raw - 10)
        else:
            direction = 'bearish'
            confidence = max(10, bearish_raw - 10)

    confidence = max(5, min(100, round(confidence, 1)))

    return {
        'direction': direction,
        'score': confidence,
        'detail': {
            'momentum_score': momentum_score,
            'vol_score': vol_score,
            'position_score': position_score,
            'pattern_score': pattern_score,
            'bullish_raw': bullish_raw,
            'bearish_raw': bearish_raw,
            'chg_5d': round(chg_5d * 100, 2),
            'chg_1d': round(chg_1d * 100, 2),
            'pos_60': round(pos * 100, 1),
            'vol_ratio': round(vol_ratio_today, 2),
            'today_up': today_up,
        },
    }


def _empty():
    return {
        'direction': 'bullish',
        'score': 0,
        'detail': {},
    }
