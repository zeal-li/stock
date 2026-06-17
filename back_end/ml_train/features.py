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


def extract_features(klines, index_klines=None):
    """从日K线列表提取特征向量

    klines: [{open, high, low, close, volume, amount, date}, ...] 按时间升序
    index_klines: 大盘指数K线列表（同上结构），可选，按时间升序

    返回: {feature_name: value} 字典
    """
    if len(klines) < 60:
        return None

    closes = [k['close'] for k in klines]
    opens = [k['open'] for k in klines]
    highs = [k['high'] for k in klines]
    lows = [k['low'] for k in klines]
    volumes = [k['volume'] for k in klines]
    amounts = [k.get('amount', 0) for k in klines]

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

    # ===== 19. 量价关系特征 (7维) =====
    # 19a. 量价相关性：近20日价格变化与成交量变化的相关性
    f['vol_price_corr_20d'] = _calc_vol_price_corr(closes, volumes, 20)

    # 19b. 涨跌量比：近20日上涨日成交量总和 / 总成交量
    vol_up = 0.0
    vol_down = 0.0
    for i in range(-20, 0):
        if closes[i] > closes[i - 1]:
            vol_up += volumes[i]
        else:
            vol_down += volumes[i]
    total_vol = vol_up + vol_down
    f['up_vol_ratio'] = vol_up / total_vol if total_vol > 0 else 0.5

    # 19c. 放量程度：当日成交量在近60日中的分位数
    if len(volumes) >= 60:
        vol_60 = sorted(volumes[-60:])
        cur_vol = volumes[-1]
        rank = sum(1 for v in vol_60 if v <= cur_vol)
        f['vol_percentile_60d'] = rank / 60.0
    else:
        f['vol_percentile_60d'] = 0.5

    # 19d. 缩量蓄力：连续缩量天数、缩量程度
    vol_shrink_days = 0
    vol_shrink_ratio = 1.0
    for i in range(len(volumes) - 1, max(len(volumes) - 10, 0), -1):
        if volumes[i] < volumes[i - 1]:
            vol_shrink_days += 1
        else:
            break
    if vol_shrink_days >= 2 and len(volumes) > vol_shrink_days:
        vol_shrink_ratio = volumes[-1] / volumes[-vol_shrink_days - 1]
    f['vol_shrink_days'] = vol_shrink_days
    f['vol_shrink_ratio'] = vol_shrink_ratio if vol_shrink_ratio != 1.0 else 1.0

    # 19e. MFI 资金流量指标 (14日)
    f['mfi_14'] = _calc_mfi(highs, lows, closes, volumes, 14)

    # ===== 20. 成交额特征：流动性/市值代理 (3维) =====
    avg_amt_5 = _ma(amounts, 5)
    avg_amt_20 = _ma(amounts, 20)
    f['amount_log'] = math.log(amounts[-1] + 1) if amounts[-1] > 0 else 0
    f['amount_ratio_5'] = (amounts[-1] / avg_amt_5) if avg_amt_5 > 0 else 1.0
    f['amount_ratio_20'] = (amounts[-1] / avg_amt_20) if avg_amt_20 > 0 else 1.0

    # ===== 20. 大盘指数对比 (8维) =====
    if index_klines:
        idx_closes = [k['close'] for k in index_klines]
        idx_dates = [k['date'] for k in index_klines]
        stock_dates = [k.get('date', '') for k in klines]
        # 日期对齐：建立 stock date -> index close 映射
        idx_map = dict(zip(idx_dates, idx_closes))
        aligned = []
        for d in stock_dates:
            aligned.append(idx_map.get(d, None))

        if len(aligned) >= 60 and all(v is not None for v in aligned[-20:]):
            # 相对收益率：stock - index
            for n in [1, 5, 10, 20]:
                if len(closes) > n and aligned[-1] and aligned[-n-1]:
                    stock_ret = closes[-1] / closes[-n-1] - 1
                    idx_ret = aligned[-1] / aligned[-n-1] - 1
                    f[f'rel_ret_{n}d'] = stock_ret - idx_ret

            # 相关性：近60日股票日收益率 vs 指数日收益率
            f['idx_corr_60d'] = _calc_correlation(closes, aligned, 60)

            # beta：近60日股票对指数的回归斜率
            f['idx_beta_60d'] = _calc_beta(closes, aligned, 60)

            # 相对位置：股票相对自身120日高点的位置 vs 指数
            if len(closes) >= 120:
                stock_high_pos = (closes[-1] - _min(closes[-120:])) / (_max(closes[-120:]) - _min(closes[-120:]) + 0.0001)
                idx_high_pos = (aligned[-1] - _min(aligned[-120:])) / (_max(aligned[-120:]) - _min(aligned[-120:]) + 0.0001)
                f['rel_high_pos'] = stock_high_pos - idx_high_pos
        else:
            for n in [1, 5, 10, 20]:
                f[f'rel_ret_{n}d'] = 0
            f['idx_corr_60d'] = 0
            f['idx_beta_60d'] = 0
            f['rel_high_pos'] = 0
    else:
        for n in [1, 5, 10, 20]:
            f[f'rel_ret_{n}d'] = 0
        f['idx_corr_60d'] = 0
        f['idx_beta_60d'] = 0
        f['rel_high_pos'] = 0

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


def _calc_correlation(closes1, closes2, period):
    """计算两组价格的日收益率在近 period 日的 Pearson 相关系数"""
    if len(closes1) < period + 1 or len(closes2) < period + 1:
        return 0
    rets1 = [math.log(closes1[i] / closes1[i-1]) for i in range(-period + 1, 1)]
    rets2 = [math.log(closes2[i] / closes2[i-1]) for i in range(-period + 1, 1)]
    n = len(rets1)
    avg1 = sum(rets1) / n
    avg2 = sum(rets2) / n
    cov = sum((rets1[i] - avg1) * (rets2[i] - avg2) for i in range(n))
    std1 = (sum((r - avg1) ** 2 for r in rets1)) ** 0.5
    std2 = (sum((r - avg2) ** 2 for r in rets2)) ** 0.5
    if std1 == 0 or std2 == 0:
        return 0
    return cov / (std1 * std2 * n)


def _calc_beta(closes1, closes2, period):
    """计算股票对指数的 beta：Cov(stock, index) / Var(index)"""
    if len(closes1) < period + 1 or len(closes2) < period + 1:
        return 1.0
    rets1 = [math.log(closes1[i] / closes1[i-1]) for i in range(-period + 1, 1)]
    rets2 = [math.log(closes2[i] / closes2[i-1]) for i in range(-period + 1, 1)]
    n = len(rets1)
    avg1 = sum(rets1) / n
    avg2 = sum(rets2) / n
    cov = sum((rets1[i] - avg1) * (rets2[i] - avg2) for i in range(n)) / n
    var2 = sum((r - avg2) ** 2 for r in rets2) / n
    if var2 == 0:
        return 1.0
    return cov / var2


def _calc_vol_price_corr(closes, volumes, period):
    """量价相关性：近 period 日价格变化率与成交量变化率的相关系数"""
    if len(closes) < period + 2 or len(volumes) < period + 2:
        return 0
    price_chg = [(closes[i] - closes[i-1]) / closes[i-1] for i in range(-period, 0) if closes[i-1] > 0]
    vol_chg = [(volumes[i] - volumes[i-1]) / volumes[i-1] for i in range(-period, 0) if volumes[i-1] > 0]
    n = min(len(price_chg), len(vol_chg))
    if n < 3:
        return 0
    avg_p = sum(price_chg[:n]) / n
    avg_v = sum(vol_chg[:n]) / n
    cov = sum((price_chg[i] - avg_p) * (vol_chg[i] - avg_v) for i in range(n))
    std_p = (sum((p - avg_p) ** 2 for p in price_chg[:n])) ** 0.5
    std_v = (sum((v - avg_v) ** 2 for v in vol_chg[:n])) ** 0.5
    if std_p == 0 or std_v == 0:
        return 0
    return cov / (std_p * std_v * n)


def _calc_mfi(highs, lows, closes, volumes, period=14):
    """MFI 资金流量指标"""
    if len(closes) < period + 1:
        return 50.0
    pos_flow = 0.0
    neg_flow = 0.0
    for i in range(-period, 0):
        tp = (highs[i] + lows[i] + closes[i]) / 3
        prev_tp = (highs[i-1] + lows[i-1] + closes[i-1]) / 3
        mf = tp * volumes[i]
        if tp > prev_tp:
            pos_flow += mf
        else:
            neg_flow += mf
    if neg_flow == 0:
        return 100.0
    mfr = pos_flow / neg_flow
    return 100.0 - 100.0 / (1.0 + mfr)
