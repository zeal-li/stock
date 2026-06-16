"""特征工程：从日K线列表提取技术指标，供训练和实时预测共用"""

import math


def _ma(values, period):
    """简单移动平均"""
    if len(values) < period:
        return 0
    return sum(values[-period:]) / period


def _ema(values, period):
    """指数移动平均"""
    if len(values) < 2:
        return values[-1] if values else 0
    k = 2.0 / (period + 1)
    ema = values[0]
    for v in values[1:]:
        ema = v * k + ema * (1 - k)
    return ema


def _std(values, period):
    """标准差"""
    if len(values) < period:
        return 0
    vals = values[-period:]
    avg = sum(vals) / period
    var = sum((v - avg) ** 2 for v in vals) / period
    return var ** 0.5


def _max(values):
    return max(values) if values else 0


def _min(values):
    return min(values) if values else 0


def extract_features(klines):
    """从日K线列表提取特征向量

    klines: [{open, high, low, close, volume, amount, date}, ...] 按时间升序

    返回: {feature_name: value} 字典
    """
    if len(klines) < 60:
        return None

    closes = [k['close'] for k in klines]
    opens = [k['open'] for k in klines]
    highs = [k['high'] for k in klines]
    lows = [k['low'] for k in klines]
    volumes = [k['volume'] for k in klines]

    last_close = closes[-1]
    f = {}

    # ===== 1. 价格与均线偏离度 (6维) =====
    for n in [5, 10, 20, 30, 60, 120]:
        ma = _ma(closes, n)
        f[f'ma{n}_deviation'] = (last_close / ma - 1) if ma > 0 else 0

    # ===== 2. 均线多头排列 (3维) =====
    # 每个值为 1 表示短期均线在长期均线上方
    f['ma5_gt_ma10'] = 1.0 if _ma(closes, 5) > _ma(closes, 10) else 0.0
    f['ma10_gt_ma20'] = 1.0 if _ma(closes, 10) > _ma(closes, 20) else 0.0
    f['ma20_gt_ma60'] = 1.0 if _ma(closes, 20) > _ma(closes, 60) else 0.0

    # ===== 3. 成交量特征 (3维) =====
    ma_vol_5 = _ma(volumes, 5)
    ma_vol_20 = _ma(volumes, 20)
    f['vol_ratio_5'] = (volumes[-1] / ma_vol_5) if ma_vol_5 > 0 else 1.0
    f['vol_ratio_20'] = (volumes[-1] / ma_vol_20) if ma_vol_20 > 0 else 1.0
    # 成交量趋势：近5日均量 / 近20日均量
    f['vol_trend'] = (ma_vol_5 / ma_vol_20) if ma_vol_20 > 0 else 1.0

    # ===== 4. 布林带 (2维) =====
    bb_mid = _ma(closes, 20)
    bb_std = _std(closes, 20)
    bb_upper = bb_mid + 2 * bb_std
    bb_lower = bb_mid - 2 * bb_std
    f['bb_position'] = ((last_close - bb_mid) / (bb_std * 2)) if bb_std > 0 else 0
    f['bb_width'] = ((bb_upper - bb_lower) / bb_mid) if bb_mid > 0 else 0

    # ===== 5. RSI (2维) =====
    f['rsi_6'] = _calc_rsi(closes, 6)
    f['rsi_14'] = _calc_rsi(closes, 14)

    # ===== 6. MACD (3维) =====
    ema12 = _ema(closes, 12)
    ema26 = _ema(closes, 26)
    dif = ema12 - ema26
    # 近似 dea
    difs = _calc_macd_difs(closes)
    dea = _ema(difs, 9) if difs else 0
    f['macd_dif'] = dif
    f['macd_dea'] = dea
    f['macd_hist'] = 2 * (dif - dea)

    # ===== 7. 价格动量：收益率 (4维) =====
    for n in [1, 5, 10, 20]:
        if len(closes) > n:
            f[f'momentum_{n}d'] = (closes[-1] / closes[-n - 1] - 1)

    # ===== 8. 波动率 (2维) =====
    f['volatility_10d'] = _calc_volatility(closes, 10)
    f['volatility_20d'] = _calc_volatility(closes, 20)

    # ===== 9. ATR / 收盘价 (1维) =====
    atr = _calc_atr(klines, 14)
    f['atr_ratio'] = (atr / last_close) if last_close > 0 else 0

    # ===== 10. 连续涨跌天数 (2维) =====
    up_days = 0; down_days = 0
    for i in range(len(closes) - 1, 0, -1):
        if closes[i] > closes[i - 1]:
            up_days += 1
        else:
            break
    for i in range(len(closes) - 1, 0, -1):
        if closes[i] < closes[i - 1]:
            down_days += 1
        else:
            break
    f['consecutive_up'] = up_days
    f['consecutive_down'] = down_days

    # ===== 11. 日内位置 (高低价位置) (1维) =====
    h_l_range = highs[-1] - lows[-1]
    f['daily_position'] = ((last_close - lows[-1]) / h_l_range) if h_l_range > 0 else 0.5

    # ===== 12. 跳空缺口 (1维) =====
    if len(klines) >= 2:
        prev_close = closes[-2]
        f['gap'] = ((opens[-1] / prev_close) - 1) if prev_close > 0 else 0
    else:
        f['gap'] = 0

    # ===== 13. 最大回撤 (2维) =====
    f['max_dd_20d'] = _calc_max_drawdown(closes, 20)
    f['max_dd_60d'] = _calc_max_drawdown(closes, 60)

    # ===== 14. 高低点相对位置 (4维) =====
    for n in [20, 60]:
        highest = _max(closes[-n:])
        lowest = _min(closes[-n:])
        rng = highest - lowest
        f[f'high_low_pos_{n}d'] = ((last_close - lowest) / rng) if rng > 0 else 0.5

        # 创新高 / 创新低
        f[f'new_high_{n}d'] = 1.0 if last_close >= highest * 0.995 else 0.0

    # ===== 15. KDJ 随机指标 (3维) =====
    k, d, j = _calc_kdj(highs, lows, closes)
    f['kdj_k'] = k
    f['kdj_d'] = d
    f['kdj_j'] = j

    # ===== 16. OBV 能量潮变化率 (1维) =====
    f['obv_roc_10'] = _calc_obv_roc(closes, volumes, 10)

    # ===== 17. CCI 商品通道指标 (2维) =====
    f['cci_14'] = _calc_cci(highs, lows, closes, 14)
    f['cci_20'] = _calc_cci(highs, lows, closes, 20)

    # ===== 18. WR 威廉指标 (1维) =====
    f['wr_14'] = _calc_wr(highs, lows, closes, 14)

    return f


def _calc_rsi(closes, period=14):
    """计算 RSI"""
    if len(closes) < period + 1:
        return 50.0
    gains = 0.0
    losses = 0.0
    for i in range(-period, 0):
        diff = closes[i] - closes[i - 1]
        if diff > 0:
            gains += diff
        else:
            losses += abs(diff)
    avg_gain = gains / period
    avg_loss = losses / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - 100.0 / (1.0 + rs)


def _calc_macd_difs(closes):
    """计算每根K线对应的 DIF (EMA12 - EMA26)"""
    if len(closes) < 26:
        return []
    ema12 = closes[0]
    ema26 = closes[0]
    k12 = 2.0 / 13
    k26 = 2.0 / 27
    difs = []
    for c in closes:
        ema12 = c * k12 + ema12 * (1 - k12)
        ema26 = c * k26 + ema26 * (1 - k26)
        difs.append(ema12 - ema26)
    return difs


def _calc_volatility(closes, period):
    """计算年化波动率（日收益率标准差 * sqrt(252)）"""
    if len(closes) < period + 1:
        return 0
    returns = [math.log(closes[i] / closes[i - 1]) for i in range(-period + 1, 0)]
    avg = sum(returns) / period
    var = sum((r - avg) ** 2 for r in returns) / (period - 1)
    return var ** 0.5 * math.sqrt(252)


def _calc_atr(klines, period=14):
    """计算 ATR"""
    if len(klines) < period + 1:
        return 0
    trs = []
    for i in range(-period, 0):
        k = klines[i]
        prev = klines[i - 1]
        tr = max(k['high'] - k['low'],
                 abs(k['high'] - prev['close']),
                 abs(k['low'] - prev['close']))
        trs.append(tr)
    return sum(trs) / period


def _calc_max_drawdown(closes, period):
    """计算最大回撤"""
    if len(closes) < period:
        return 0
    vals = closes[-period:]
    peak = vals[0]
    max_dd = 0.0
    for v in vals:
        if v > peak:
            peak = v
        dd = (peak - v) / peak if peak > 0 else 0
        if dd > max_dd:
            max_dd = dd
    return max_dd


def _calc_kdj(highs, lows, closes, n=9):
    """KDJ 随机指标，返回 (K, D, J)"""
    if len(closes) < n + 1:
        return 50.0, 50.0, 50.0
    k = 50.0
    d = 50.0
    for i in range(n, len(closes)):
        low_n = min(lows[i - n:i])
        high_n = max(highs[i - n:i])
        rng = high_n - low_n
        rsv = ((closes[i] - low_n) / rng * 100) if rng > 0 else 50.0
        k = 2/3 * k + 1/3 * rsv
        d = 2/3 * d + 1/3 * k
    j = 3 * k - 2 * d
    return round(k, 4), round(d, 4), round(j, 4)


def _calc_obv_roc(closes, volumes, period=10):
    """OBV 能量潮 N 日变化率"""
    if len(closes) < 2:
        return 0
    obv_series = []
    obv = 0
    for i in range(len(closes)):
        if i == 0:
            obv = volumes[0]
        elif closes[i] > closes[i - 1]:
            obv += volumes[i]
        elif closes[i] < closes[i - 1]:
            obv -= volumes[i]
        obv_series.append(obv)
    if len(obv_series) < period + 1 or obv_series[-period - 1] == 0:
        return 0
    return obv_series[-1] / obv_series[-period - 1] - 1


def _calc_cci(highs, lows, closes, n=14):
    """CCI 商品通道指标"""
    if len(closes) < n:
        return 0
    tp_list = [(highs[i] + lows[i] + closes[i]) / 3 for i in range(-n, 0)]
    tp_ma = sum(tp_list) / n
    md = sum(abs(tp - tp_ma) for tp in tp_list) / n
    if md == 0:
        return 0
    tp_now = (highs[-1] + lows[-1] + closes[-1]) / 3
    return round((tp_now - tp_ma) / (0.015 * md), 4)


def _calc_wr(highs, lows, closes, n=14):
    """WR 威廉指标 (0 ~ -100，转为正值)"""
    if len(closes) < n:
        return -50.0
    high_n = max(highs[-n:])
    low_n = min(lows[-n:])
    rng = high_n - low_n
    if rng == 0:
        return -50.0
    wr = (high_n - closes[-1]) / rng * -100
    return round(wr, 4)
