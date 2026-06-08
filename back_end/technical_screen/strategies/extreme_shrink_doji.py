"""极致缩量十字星选股策略
检测标准：
  1. 严格十字星：实体 < 振幅的8%，且整根K线振幅 < 3%
  2. 连续明显缩量：成交量 < 前一日80% 且 < 前5日均量70%
  3. 近期地量：成交量在20日内最低或次低
  4. 上下影线均衡且不长（单边影线振幅 < 2%）
  5. 价格处于近期相对低位，缩量变盘信号更有意义
"""


def calc(klines, lookback=60):
    if len(klines) < max(lookback, 20):
        return 0, {}

    window = klines[-lookback:]
    latest = window[-1]

    o = latest['open']
    c = latest['close']
    h = latest['high']
    l = latest['low']
    v = latest['volume']

    # ====== 1. 严格十字星 ======
    body = abs(c - o)
    full_range = h - l
    if full_range <= 0:
        return 0, {}

    body_ratio = body / full_range

    # 实体必须 < 8%（严格十字星）
    if body_ratio > 0.08:
        return 0, {}

    # 整根K线振幅 < 3%（极致缩量十字星应该是窄幅波动，不是长影线十字星）
    amplitude = full_range / l
    if amplitude > 0.03:
        return 0, {}

    # 必须有上下影线（排除一字板/涨停/跌停）
    upper_shadow = h - max(o, c)
    lower_shadow = min(o, c) - l
    if upper_shadow <= 0 or lower_shadow <= 0:
        return 0, {}

    # 单边影线振幅 < 1.8%（不是长影线十字星）
    upper_amp = upper_shadow / l
    lower_amp = lower_shadow / l
    if upper_amp > 0.018 or lower_amp > 0.018:
        return 0, {}

    # 最低振幅要求（排除织布机）
    if amplitude < 0.005:
        return 0, {}

    # ====== 2. 连续明显缩量 ======
    volumes = [k['volume'] for k in window]

    # 前一日成交量
    if len(window) < 2:
        return 0, {}
    prev_vol = volumes[-2]
    if prev_vol <= 0:
        return 0, {}

    # 对比前一日：必须明显缩量（<80%）
    vol_vs_prev = v / prev_vol
    if vol_vs_prev > 0.8:
        return 0, {}

    # 对比前5日均量（不含今天）
    recent_vols = volumes[-6:-1]  # 前5天
    avg_vol_5 = sum(recent_vols) / len(recent_vols) if recent_vols else prev_vol
    if avg_vol_5 <= 0:
        return 0, {}
    vol_vs_5 = v / avg_vol_5

    # 必须 < 前5日均量的70%
    if vol_vs_5 > 0.7:
        return 0, {}

    # 对比20日均量（不含今天）
    avg_vol_20 = sum(volumes[-21:-1]) / 20 if len(volumes) >= 21 else avg_vol_5
    if avg_vol_20 <= 0:
        return 0, {}
    vol_vs_20 = v / avg_vol_20

    # ====== 3. 近期地量 ======
    sorted_vols = sorted(volumes[-21:])
    vol_rank = sorted_vols.index(v)  # 0 = 最低
    is_ground_volume = vol_rank <= 1  # 20日内最低或次低

    # ====== 4. 价格位置 ======
    high_20 = max(k['high'] for k in window[-20:])
    low_20 = min(k['low'] for k in window[-20:])
    if high_20 <= low_20:
        return 0, {}
    price_pos = (c - low_20) / (high_20 - low_20)

    # 优先低位缩量（低位十字星才是变盘信号，高位可能是滞涨）
    if price_pos > 0.65:
        return 0, {}

    # ====== 5. 近期趋势 ======
    closes = [k['close'] for k in window]
    ma5 = sum(closes[-6:-1]) / 5
    ma20 = sum(closes[-21:-1]) / 20 if len(closes) >= 21 else ma5
    ma5_prev = sum(closes[-7:-2]) / 5 if len(closes) >= 7 else ma5

    # 趋势：横盘或缓跌最好（加速下跌的不行）
    trend_5 = (ma5 - ma5_prev) / ma5_prev if ma5_prev > 0 else 0
    if trend_5 < -0.03:  # 5日跌幅超过3%不选
        return 0, {}

    # ====== 6. 评分 ======
    score = 0

    # 实体越小越好（0-15分）
    score += max(0, (0.08 - body_ratio) / 0.08 * 15)

    # 振幅越小越好（0-15分）
    score += max(0, (0.03 - amplitude) / 0.03 * 15)

    # 对比前一日缩量越极致分越高（0-20分）
    score += max(0, (0.8 - vol_vs_prev) / 0.8 * 20)

    # 对比前5日均量缩量（0-20分）
    score += max(0, (0.7 - vol_vs_5) / 0.7 * 20)

    # 地量加成（最低5分，次低2分）
    if is_ground_volume:
        score += 5 if vol_rank == 0 else 2

    # 影线对称性（0-10分）
    total_shadow = upper_shadow + lower_shadow
    if total_shadow > 0:
        score += (1 - abs(upper_shadow - lower_shadow) / total_shadow) * 10

    # 价格位置（0-10分）：越低越好
    score += max(0, (0.65 - price_pos) / 0.65 * 10)

    # 横盘加分（0-5分）
    if abs(trend_5) <= 0.01:
        score += 5

    score = round(min(score, 100), 1)
    if score < 40:
        return 0, {}

    return score, {
        'body_ratio': round(body_ratio * 100, 1),
        'amplitude': round(amplitude * 100, 2),
        'vol_ratio': round(vol_vs_20, 2),
        'price_pos': round(price_pos * 100, 1),
        'ground_vol': is_ground_volume,
    }
