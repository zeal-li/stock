"""通用格式化函数"""

from datetime import datetime, timedelta, time

# 市场开盘/收盘时间配置（北京时间）
MARKET_HOURS = {
    'hs_main':  {'open': (9, 30),  'close': (15, 0)},
    'hs_etf':   {'open': (9, 30),  'close': (15, 0)},
    'gem':      {'open': (9, 30),  'close': (15, 0)},
    'star':     {'open': (9, 30),  'close': (15, 0)},
    'hk_main':  {'open': (9, 30),  'close': (16, 0)},
    'us_main':  {'open': (21, 30), 'close': (4, 0)},   # 美股夏令时 21:30-04:00
}

# market code → seg_key 映射（用于通过 market code 查市场时间）
_MARKET_TO_SEG = {
    '0': 'hs_main',   # 深交所主板
    '1': 'hs_main',   # 上交所主板
    '2': 'hs_etf',    # 场内基金
    '90': 'gem',      # 创业板/科创板
    '116': 'hk_main', # 港股
    '106': 'us_main', # 美股
}


def to_minutes(h, m):
    """小时:分钟 → 当天的分钟数"""
    return h * 60 + m


def is_cross_day(open_h, open_m, close_h, close_m):
    """收盘时间是否在次日（如美股 21:30 开盘，次日 04:00 收盘）"""
    return close_h < open_h or (close_h == open_h and close_m < open_m)


def is_before_open(dt, open_h, open_m, is_cross_day=False):
    """判断时间是否在开盘前"""
    dt_min = to_minutes(dt.hour, dt.minute)
    open_min = to_minutes(open_h, open_m)
    return dt_min < open_min


def is_after_close(dt, close_h, close_m, open_h, open_m, is_cross_day=False):
    """判断时间是否在收盘后"""
    dt_min = to_minutes(dt.hour, dt.minute)
    close_min = to_minutes(close_h, close_m)
    open_min = to_minutes(open_h, open_m)
    if is_cross_day:
        # 美股收盘在次日凌晨: 收盘后 = dt_min >= close_min 且 dt_min < open_min
        return dt_min >= close_min and dt_min < open_min
    return dt_min >= close_min


def is_trading_hours(dt, open_h, open_m, close_h, close_m, is_cross_day=False):
    """判断时间是否在交易时段内"""
    dt_min = to_minutes(dt.hour, dt.minute)
    open_min = to_minutes(open_h, open_m)
    close_min = to_minutes(close_h, close_m)
    if is_cross_day:
        return dt_min >= open_min or dt_min < close_min
    return open_min <= dt_min < close_min


def is_market_opened(market):
    """判断指定市场今天是否已开盘。
    - A股: 9:30 开盘
    - 港股: 9:30 开盘
    - 美股: 21:30 开盘（北京时间）
    周末视为未开盘。
    market: '0'/'1'/'2'/'90' A股, '116' 港股, '106' 美股
    """
    now = datetime.now()
    if now.weekday() >= 5:
        return False
    seg = _MARKET_TO_SEG.get(str(market))
    if not seg:
        return False
    hours = MARKET_HOURS[seg]
    open_min = to_minutes(*hours['open'])
    return to_minutes(now.hour, now.minute) >= open_min


def is_a_trading_time():
    """判断当前是否在A股交易时段（周一至周五 09:15-11:35, 12:55-15:05）"""
    now = datetime.now()
    if now.weekday() >= 5:
        return False
    t = now.hour * 60 + now.minute
    return (555 <= t <= 695) or (775 <= t <= 905)


def effective_today_str():
    """返回有效的"今天"日期字符串(YYYY-MM-DD)：开盘前(<9:00)退回昨天"""
    now = datetime.now()
    if now.weekday() < 5 and now.hour < 9:
        return (now - timedelta(days=1)).strftime('%Y-%m-%d')
    return now.strftime('%Y-%m-%d')


def get_market_hours(seg_key):
    """获取指定 seg_key 的开盘/收盘时间，返回 (open_h, open_m, close_h, close_m, is_cross_day)"""
    hours = MARKET_HOURS.get(seg_key)
    if not hours:
        return None
    open_h, open_m = hours['open']
    close_h, close_m = hours['close']
    cross = is_cross_day(open_h, open_m, close_h, close_m)
    return open_h, open_m, close_h, close_m, cross

def is_etf(code, market):
    """判断是否为场内基金（ETF+LOF），价格显示3位小数"""
    c = str(code) if code else ''
    # 深ETF: 159开头
    if c[:3] == '159':
        return True
    # 深LOF: 160~168开头
    if c[:2] in ('16', '17', '18'):
        return True
    # 沪ETF: 51/56/58开头
    if c[:2] in ('51', '56', '58'):
        return True
    # 沪LOF: 50开头（其他沪市场内基金）
    if c[:2] == '50':
        return True
    return False


def fmt(v, is_etf=False):
    if v is None or v == '-' or v == '': return '-'
    try: return f"{float(v):.3f}" if is_etf else f"{float(v):.2f}"
    except: return str(v)


def fmt_pct(v):
    if v is None or v == '-' or v == '': return '-'
    try: return f"{float(v):.2f}%"
    except: return str(v)


def fmt_volume(v, market=None):
    if v is None or v == '-' or v == '': return '-'
    try:
        v = float(v)
        market = str(market) if market is not None else ''
        if market in ('0', '1', '2', '90'):
            v *= 100
        if v >= 1e8: return f"{v/1e8:.2f}亿股"
        if v >= 1e4: return f"{v/1e4:.2f}万股"
        return f"{v:.0f}股"
    except: return str(v)


def fmt_amount(v):
    if v is None or v == '-' or v == '': return '-'
    try:
        v = float(v)
        if v >= 1e8: return f"{v/1e8:.2f}亿"
        if v >= 1e4: return f"{v/1e4:.2f}万"
        return f"{v:.0f}"
    except: return str(v)


def fmt_cap(v):
    if v is None or v == '-' or v == '': return '-'
    try:
        v = float(v)
        if v >= 1e12: return f"{v/1e12:.2f}万亿"
        if v >= 1e8: return f"{v/1e8:.2f}亿"
        return f"{v/1e4:.2f}万"
    except: return str(v)
