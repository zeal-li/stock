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
    1. 短期动量 (35) — 近5日价格走势、今日涨跌、缺口、日内收盘位置、连阳连阴
    2. 量价关系 (30) — 量能配合程度、量能趋势、Effort vs Result
    3. 位置高低 (20) — 60日/120日波动区间内的相对位置
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

    # ============================================================
    # 前置计算：新增指标
    # ============================================================

    # -- ATR（14日平均真实波幅）用于波动率校准 --
    tr_list = []
    for i in range(-14, 0):
        if i - 1 >= -len(closes):
            pc = closes[i - 1]
        else:
            pc = closes[i]
        h, l = highs[i], lows[i]
        tr = max(h - l, abs(h - pc), abs(l - pc))
        tr_list.append(tr)
    atr = sum(tr_list) / len(tr_list) if tr_list else 0.01
    atr_pct = atr / cur_close if cur_close > 0 else 0.01

    avg_vol_5 = _ma(volumes, 5) or cur_vol
    avg_vol_20 = _ma(volumes, 20) or avg_vol_5

    # -- 收盘在日内振幅区间的位置 (0=最低点, 1=最高点) --
    day_range = cur_high - cur_low
    if day_range > 0:
        close_pos_in_range = (cur_close - cur_low) / day_range
        close_pos_in_range = max(0, min(1, close_pos_in_range))
    else:
        close_pos_in_range = 0.5

    # -- 缺口分析 --
    gap_pct = 0
    if len(closes) >= 2:
        prev_close = closes[-2]
        if prev_close > 0:
            gap_pct = (cur_open - prev_close) / prev_close

    # -- 量能趋势（5日均量 vs 20日均量，>1 扩张，<1 萎缩） --
    vol_trend = avg_vol_5 / avg_vol_20 if avg_vol_20 and avg_vol_20 > 0 else 1

    # -- 连阳/连阴天数 --
    consecutive_up = 0
    consecutive_down = 0
    for i in range(-1, -min(len(closes), 10) - 1, -1):
        day_up = closes[i] >= opens[i]
        if day_up and consecutive_down == 0:
            consecutive_up += 1
        elif not day_up and consecutive_up == 0:
            consecutive_down += 1
        else:
            break

    # -- NR7（7日最窄振幅，波动率压缩预示即将变盘） --
    cur_range_pct = day_range / cur_open if cur_open > 0 else 0
    is_nr7 = True
    for i in range(-7, -1):
        if i >= -len(klines):
            prev_h, prev_l = highs[i], lows[i]
            prev_c = closes[i] if closes[i] > 0 else 1
            prev_range_pct = (prev_h - prev_l) / prev_c
            if prev_range_pct < cur_range_pct:
                is_nr7 = False
                break
        else:
            is_nr7 = False
            break

    # -- 均线（预计算供多处使用） --
    ma5 = _ma(closes, 5)
    ma10 = _ma(closes, 10)
    ma20_val = _ma(closes, 20)

    # -- 价格偏离 MA20 幅度（均值回归力） --
    ma20_dist = (cur_close - ma20_val) / ma20_val if ma20_val and ma20_val > 0 else 0

    # -- 60日/120日位置（预计算供动量因子使用） --
    h60 = max(highs[-60:]) if len(highs) >= 60 else max(highs)
    l60 = min(lows[-60:]) if len(lows) >= 60 else min(lows)
    pos = (cur_close - l60) / (h60 - l60) if h60 > l60 else 0.5

    pos_120 = None
    if len(highs) >= 120:
        h120 = max(highs[-120:])
        l120 = min(lows[-120:])
        if h120 > l120:
            pos_120 = (cur_close - l120) / (h120 - l120)

    # -- Inside Day / Outside Day --
    is_inside = False
    is_outside = False
    if len(klines) >= 2:
        prev_high = highs[-2]
        prev_low = lows[-2]
        is_inside = cur_high <= prev_high and cur_low >= prev_low
        is_outside = cur_high > prev_high and cur_low < prev_low

    # -- 量能高潮：今日量是否为近20日最高 --
    is_vol_climax = cur_vol >= max(volumes[-20:]) if len(volumes) >= 20 else False

    # -- 距20日前高距离（阻力位，不含今日） --
    h20_ex = max(highs[-21:-1]) if len(highs) >= 21 else max(highs[:-1]) if len(highs) > 1 else cur_high
    dist_to_h20 = (h20_ex - cur_close) / cur_close if cur_close > 0 else 1
    near_resistance = cur_high < h20_ex and 0 < dist_to_h20 < 0.03  # 未创前高且3%内

    # -- 跳空频率：近15日内跳空高开次数 --
    recent_gap_ups = 0
    for i in range(-1, -min(len(closes), 16), -1):
        if i - 1 >= -len(closes):
            prev_c = closes[i - 1]
            g = (opens[i] - prev_c) / prev_c if prev_c > 0 else 0
            if g > 0.015:  # 跳空高开 >1.5%
                recent_gap_ups += 1

    # ============================================================
    # 1. 短期动量 (35分)
    # ============================================================
    momentum_score = 0

    # 近5日涨跌幅
    chg_1d = (closes[-1] - closes[-2]) / closes[-2] if len(closes) >= 2 else 0
    chg_5d = (closes[-1] - closes[-6]) / closes[-6] if len(closes) >= 6 else 0
    chg_3d = (closes[-1] - closes[-4]) / closes[-4] if len(closes) >= 4 else 0

    # 今日涨跌（收阳 vs 收阴）
    today_up = cur_close >= cur_open
    today_body_pct = (cur_close - cur_open) / cur_open if cur_open > 0 else 0

    # -- 5日涨幅 --
    if 0.005 < chg_5d <= 0.04:       # 温和上涨 0.5%-4%
        momentum_score += 12
    elif 0.002 < chg_5d <= 0.005:     # 微涨
        momentum_score += 7
    elif -0.01 < chg_5d <= 0.002:     # 横盘微涨
        momentum_score += 4
    elif -0.02 < chg_5d <= -0.01:     # 小幅下跌
        momentum_score -= 5
    elif chg_5d <= -0.02:             # 明显下跌
        momentum_score -= 12

    # -- 今日涨跌 --
    if chg_1d > 0:
        if 0.01 < chg_1d <= 0.03:     # 今日涨1-3%，动能健康
            momentum_score += 7
        elif 0 < chg_1d <= 0.01:       # 小涨
            momentum_score += 4
        elif chg_1d > 0.05:            # 涨幅过大，统计上易回调
            momentum_score -= 2
    elif chg_1d < -0.04:               # 今日大跌 >4%
        momentum_score -= 10
    elif chg_1d < -0.02:               # 今日中跌 2-4%
        momentum_score -= 6
    elif chg_1d < 0:                   # 微跌
        momentum_score -= 3

    # -- ATR 校准：用自身波动率衡量涨跌幅的显著性 --
    if atr_pct > 0:
        chg_5d_atr = chg_5d / atr_pct
        if 0.5 < chg_5d_atr <= 4:         # 相对自身波动温和上涨
            momentum_score += 2
        elif chg_5d_atr > 6:               # 涨幅远超正常波动范围
            momentum_score -= 4
        elif chg_5d_atr < -4:              # 跌幅远超正常波动范围
            momentum_score -= 5

    # -- 收盘在日内位置 --
    if close_pos_in_range > 0.8 and today_up:
        momentum_score += 4           # 收在日内高位，尾盘强势
    elif close_pos_in_range > 0.7 and today_up:
        momentum_score += 2           # 偏强收盘
    elif close_pos_in_range < 0.25 and not today_up:
        momentum_score -= 5           # 收在日内低位，尾盘跳水
    elif close_pos_in_range < 0.35 and not today_up:
        momentum_score -= 3           # 偏弱收盘
    elif close_pos_in_range < 0.35 and today_up:
        momentum_score -= 3           # 虽收阳但尾盘跳水（高开低走）
    elif close_pos_in_range > 0.7 and not today_up:
        momentum_score += 2           # 虽收阴但尾盘拉回（低开高走）

    # -- 缺口分析 --
    if gap_pct > 0.02 and today_up and close_pos_in_range > 0.7:
        momentum_score += 6           # 向上跳空高开 + 收阳不补缺口 = 强势突破
    elif gap_pct < -0.02 and not today_up and close_pos_in_range < 0.3:
        momentum_score -= 8           # 向下跳空低开 + 收阴不补缺口 = 弱势破位
    elif gap_pct > 0.02 and not today_up:
        momentum_score -= 5           # 高开低走 = 诱多
    elif gap_pct < -0.02 and today_up:
        momentum_score += 5           # 低开高走 = 反转信号

    # -- 3日趋势方向一致性 --
    chg_1 = (closes[-1] - closes[-2]) / closes[-2] if len(closes) >= 2 else 0
    chg_2 = (closes[-2] - closes[-3]) / closes[-3] if len(closes) >= 3 else 0
    chg_3 = (closes[-3] - closes[-4]) / closes[-4] if len(closes) >= 4 else 0
    up_days = sum(1 for c in [chg_1, chg_2, chg_3] if c > 0)
    if up_days >= 2:
        momentum_score += 7
    elif up_days == 0:
        momentum_score -= 5

    # -- 连阳/连阴天数 --
    if consecutive_up >= 4:
        momentum_score -= 3           # 4连阳以上，回调概率增大
    elif consecutive_up >= 3:
        momentum_score += 1           # 3连阳，动量延续，但空间收窄
    if consecutive_down >= 5:
        momentum_score += 3           # 5连阴，超卖反弹预期
    elif consecutive_down >= 3:
        momentum_score -= 3           # 3-4连阴，弱势延续

    # -- 连涨后衰竭 --
    if chg_3d > 0.01 and chg_1d < -0.03:
        momentum_score -= 12

    # -- NR7 振幅压缩（波动率收缩→即将变盘） --
    if is_nr7:
        if today_up and pos < 0.5:
            momentum_score += 4   # 低位 NR7 收阳 = 大概率向上突破
        elif not today_up and pos > 0.6:
            momentum_score -= 5   # 高位 NR7 收阴 = 大概率向下破位
        elif today_up:
            momentum_score += 2   # NR7 收阳，偏多
        else:
            momentum_score -= 3   # NR7 收阴，偏空

    # -- 均线回归力（偏离 MA20 幅度） --
    if ma20_dist > 0.15:
        momentum_score -= 6       # 严重高于均线，均值回归引力强
    elif ma20_dist > 0.10:
        momentum_score -= 3       # 偏远离
    elif ma20_dist < -0.10:
        if today_up:
            momentum_score += 3   # 深度超跌 + 收阳 = 反弹启动
        else:
            momentum_score -= 2   # 深度超跌还在跌
    elif ma20_dist < -0.05 and today_up:
        momentum_score += 2       # 轻度超跌反弹

    momentum_score = max(0, min(35, momentum_score))

    # ============================================================
    # 2. 量价关系 (30分，范围 -15 ~ 30)
    # ============================================================
    vol_score = 0  # 从0开始，不做偏向看涨的假设

    vol_ratio_today = cur_vol / avg_vol_5 if avg_vol_5 > 0 else 1
    vol_ratio_20 = cur_vol / avg_vol_20 if avg_vol_20 > 0 else 1

    # -- 基本量价组合 --
    # 价升量增（强势信号，但过热时可能是散户追涨）
    if today_up and vol_ratio_today > 1.2:
        vol_score += 9
    elif today_up and vol_ratio_today > 1.0:
        vol_score += 5
    # 价跌量缩（止跌信号）
    elif not today_up and vol_ratio_today < 0.8:
        vol_score += 8
    # 价跌量正常 — 承接真空：正常卖出、无人接盘，最危险
    elif not today_up and 0.8 <= vol_ratio_today <= 1.1:
        vol_score -= 8
    # 价跌微放量
    elif not today_up and 1.1 < vol_ratio_today <= 1.3:
        vol_score -= 5
    # 价跌放量 — 区分微跌放量（滞跌出货）vs 大跌放量（恐慌抛售）
    elif not today_up and vol_ratio_today > 1.3:
        if chg_1d > -0.03:              # 微跌放量 = 托着出货，更阴险
            vol_score -= 12
        else:                             # 大跌放量 = 恐慌抛售
            vol_score -= 10
    # 价升量缩（动能衰减）
    elif today_up and vol_ratio_today < 0.7:
        vol_score -= 5

    # -- 量能趋势（扩张 vs 萎缩） --
    if vol_trend > 1.05:
        if today_up and vol_ratio_today > 1.0:
            vol_score += 2           # 趋势扩张 + 今日放量上涨 = 真放量
        elif not today_up:
            vol_score -= 3           # 趋势扩张但收阴 = 放量下跌
    elif vol_trend < 0.75:
        vol_score -= 2               # 持续冰点缩量，人气涣散

    # -- Effort vs Result（威科夫）：高 effort 低 result = churning --
    if vol_ratio_today > 1.3 and abs(chg_1d) < 0.015:
        if today_up:
            vol_score -= 8           # 放量但几乎不涨 = 滞涨出货
        else:
            vol_score += 5           # 放量但几乎不跌 = 有人兜底承接

    # -- 近5日量价同步性 --
    sync_count = 0
    for i in range(-5, 0):
        day_up = closes[i] >= opens[i]
        day_vol_ratio = volumes[i] / avg_vol_20 if avg_vol_20 > 0 else 1
        if day_up and day_vol_ratio > 1.0:
            sync_count += 1
        elif not day_up and day_vol_ratio < 1.0:
            sync_count += 1
    vol_score += min(sync_count, 3) * 1   # 最多 +3

    vol_score = max(-15, min(30, vol_score))

    # ============================================================
    # 3. 位置高低 (20分)
    # ============================================================

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

    # -- 120日位置交叉验证 --
    if pos_120 is not None:
        if pos > 0.8 and pos_120 < 0.5:
            position_score += 5   # 60日高位 + 120日中低位 = 假高位，实际还在底部区域
        elif pos < 0.15 and pos_120 > 0.6:
            position_score -= 3   # 60日低位 + 120日高位 = 假低位，可能是下跌中继
        elif pos < 0.15 and pos_120 < 0.25:
            position_score += 3   # 60日+120日双低 = 真底部区域

    # -- 均线位置加分项 --
    if ma5 and ma10 and ma20_val:
        if cur_close > ma5 > ma10:         # 均线多头
            position_score += 2

    position_score = min(20, position_score)

    # ============================================================
    # 4. K线形态 (15分，范围 -8 ~ 15)
    # ============================================================
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
            pattern_score += 10
        else:
            pattern_score += 4

    # 十字星/十字线（实体极小）
    if body_pct < 0.002 and shadow_ratio > 0.01:
        pattern_score += 5

    # 射击之星/倒锤子（上影线长，高位）
    if upper_shadow > body * 2 and lower_shadow < body * 0.5:
        if pos > 0.65:
            pattern_score -= 8   # 高位射击之星，看跌

    # 光头阳线（收在最高点附近）
    if today_up and upper_shadow < body * 0.2:
        if 0.01 <= today_body_pct <= 0.04:
            pattern_score += 8
        else:
            pattern_score += 4

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
                pattern_score += 9
            else:
                pattern_score += 5

    # -- Inside Day（包线蓄力，振幅被昨日完全包含） --
    if is_inside:
        if today_up and pos < 0.5:
            pattern_score += 3   # 低位蓄力，准备突破
        elif today_up:
            pattern_score += 1   # 一般蓄力

    # -- Outside Day（穿头破脚，振幅完全超出昨日） --
    if is_outside:
        if today_up:
            pattern_score += 6   # 看涨 OS day = 强突破
            if pos < 0.5:
                pattern_score += 2   # 低位 OS day 更强
        else:
            pattern_score -= 7   # 看跌 OS day = 破位

    pattern_score = max(-8, min(15, pattern_score))

    # ============================================================
    # 综合判定
    # ============================================================

    # -- 动量衰减检测：5日涨幅大部分集中在早期，近期滞涨 --
    momentum_deceleration = False
    if chg_5d > 0.015 and chg_1d < chg_5d * 0.25:
        momentum_deceleration = True  # 涨幅多由前几天贡献，今天涨不动了

    # -- 均值回归惩罚 --
    mean_reversion_penalty = 0
    if pos > 0.75 and momentum_score >= 15:
        # 高位置 + 还有动量 = 统计上回调概率高
        mean_reversion_penalty = int((pos - 0.5) * 15) + (momentum_score - 10) // 4
    if momentum_deceleration and pos > 0.6:
        mean_reversion_penalty += int((pos - 0.4) * 10)

    # -- 看涨总分 --
    bullish_raw = momentum_score + vol_score + position_score + pattern_score - mean_reversion_penalty
    bullish_raw = max(0, min(100, bullish_raw))

    # -- 看跌方向信号 --
    # 位置因子
    if pos > 0.80:
        bearish_position = min(18, int((pos - 0.5) * 36))
    elif pos > 0.70:
        bearish_position = min(12, int((pos - 0.5) * 25))
    elif pos > 0.6:
        bearish_position = 5
    else:
        bearish_position = 0

    if pos_120 is not None and pos_120 > 0.75:
        bearish_position = min(22, bearish_position + 8)

    # 动量反向
    if chg_5d < -0.03:
        bearish_momentum = min(20, int(abs(chg_5d) * 300))
    elif chg_5d < -0.01:
        bearish_momentum = 8
    else:
        bearish_momentum = 0

    # 连阴加速看跌
    if consecutive_down >= 4:
        bearish_momentum = min(25, bearish_momentum + 6)

    # 动量衰减 + 中高位
    if momentum_deceleration and pos > 0.55:
        bearish_momentum = min(25, bearish_momentum + int((pos - 0.4) * 15))

    # 连阳过热
    if consecutive_up >= 4:
        bearish_momentum = min(25, bearish_momentum + int(consecutive_up * 1.5))

    # 缺口向下不补
    if gap_pct < -0.02 and close_pos_in_range < 0.3:
        bearish_momentum = min(25, bearish_momentum + 8)

    # NR7 高位收阴
    if is_nr7 and not today_up and pos > 0.55:
        bearish_momentum = min(25, bearish_momentum + 6)

    # 量价反向
    if not today_up and vol_ratio_today > 1.2:
        bearish_vol = min(15, int(vol_ratio_today * 10))
    elif not today_up and vol_ratio_today > 0.9:
        bearish_vol = 3
    else:
        bearish_vol = 0

    # -- 高位 + 量能高潮 = 放量见顶（distribution day）
    if is_vol_climax and pos > 0.55 and today_up:
        bearish_vol = min(25, bearish_vol + 12)

    # 高位 churning
    if pos > 0.65 and vol_ratio_today > 1.3 and abs(chg_1d) < 0.015:
        bearish_vol = min(20, bearish_vol + 10)

    # -- 阻力位：贴近前高无法突破 --
    if near_resistance and pos > 0.55:
        bearish_position = min(25, bearish_position + int(dist_to_h20 * 200))

    # -- 多次跳空透支 --
    if recent_gap_ups >= 3:
        bearish_momentum = min(30, bearish_momentum + 10)
    elif recent_gap_ups >= 2 and pos > 0.5:
        bearish_momentum = min(25, bearish_momentum + 6)

    bearish_pattern = abs(min(0, pattern_score)) if pattern_score < 0 else 0

    bearish_raw = bearish_position + bearish_momentum + bearish_vol + bearish_pattern
    bearish_raw = min(100, bearish_raw)

    # -- 中短期趋势偏置：空头排列 + 持续下跌 → 压制看涨 --
    trend_bias = 0
    chg_20d = (closes[-1] - closes[-20]) / closes[-20] if len(closes) >= 20 else 0
    # MA空头排列仅在20日回报为负时才生效
    if ma5 and ma10 and ma20_val and chg_20d < -0.02:
        if cur_close < ma5 < ma10 < ma20_val:
            trend_bias = -7
        elif cur_close < ma5 < ma10:
            trend_bias = -5
        elif cur_close < ma20_val and ma5 < ma10:
            trend_bias = -3
    # 20日跌幅独立触发
    if chg_20d < -0.12:
        trend_bias = min(trend_bias, -8)
    elif chg_20d < -0.08:
        trend_bias = min(trend_bias, -5)
    elif chg_20d < -0.04:
        trend_bias = min(trend_bias, -3)

    if trend_bias < 0:
        bullish_raw = max(0, bullish_raw + trend_bias)
        bearish_raw = min(100, bearish_raw + abs(trend_bias))

    # -- 方向判定 & 置信度 --
    gap = bullish_raw - bearish_raw
    if abs(gap) >= 10:
        if gap > 0:
            direction = 'bullish'
            leader = bullish_raw
        else:
            direction = 'bearish'
            leader = bearish_raw
        confidence = leader - abs(gap) * 0.15
    else:
        if bullish_raw >= bearish_raw:
            direction = 'bullish'
            confidence = max(3, bullish_raw - 6)
        else:
            direction = 'bearish'
            confidence = max(3, bearish_raw - 6)

    confidence = max(3, min(100, round(confidence, 1)))

    return {
        'direction': direction,
        'score': confidence,
        'detail': {
            'momentum_score': momentum_score,
            'vol_score': vol_score,
            'position_score': position_score,
            'pattern_score': pattern_score,
            'mr_penalty': mean_reversion_penalty,
            'trend_bias': trend_bias,
            'bullish_raw': bullish_raw,
            'bearish_raw': bearish_raw,
            'chg_5d': round(chg_5d * 100, 2),
            'chg_1d': round(chg_1d * 100, 2),
            'pos_60': round(pos * 100, 1),
            'pos_120': round(pos_120 * 100, 1) if pos_120 is not None else None,
            'vol_ratio': round(vol_ratio_today, 2),
            'vol_trend': round(vol_trend, 2),
            'atr_pct': round(atr_pct * 100, 2),
            'gap_pct': round(gap_pct * 100, 2),
            'close_pos': round(close_pos_in_range * 100, 1),
            'consecutive_up': consecutive_up,
            'consecutive_down': consecutive_down,
            'is_nr7': is_nr7,
            'ma20_dist': round(ma20_dist * 100, 2),
            'is_inside': is_inside,
            'is_outside': is_outside,
            'is_vol_climax': is_vol_climax,
            'near_resistance': near_resistance,
            'recent_gap_ups': recent_gap_ups,
            'today_up': today_up,
        },
    }


def _empty():
    return {
        'direction': 'bullish',
        'score': 0,
        'detail': {},
    }
