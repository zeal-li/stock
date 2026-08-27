"""通用格式化函数 & 市场常量"""

from datetime import datetime, timedelta, time

# ========================= 市场常量 =========================
# market code → 数据源前缀（各功能模块统一引用，不再各自写死）

# 新浪行情前缀
SINA_PREFIX = {'1': 'sh', '0': 'sz', '2': 'bj', '90': 'sz'}

# 东方财富 F10 前缀（概念题材/主营业务 API）
EM_F10_PREFIX = {'0': 'SZ', '1': 'SH', '2': 'BJ', '90': 'SZ'}

# 同花顺 K线 API 前缀
THS_PREFIX = {'0': 'sz', '1': 'sh', '2': 'sh', '90': 'sh'}

# Yahoo Finance 代码构造
YAHOO_PREFIX = {'116': '.HK', '106': ''}


# ========================= 市场分类 =========================

def is_a_share(market):
    """A股（深/沪/北/板块）"""
    return str(market) in ('0', '1', '2', '90')

def is_hk(market):
    """港股"""
    return str(market) == '116'

def is_us(market):
    """美股"""
    return str(market) == '106'

def is_overseas(market):
    """港股或美股"""
    return str(market) in ('116', '106')


# ========================= 成交量/代码转换 =========================

def adjust_volume(vol, market):
    """A股成交量为手，转为股；港股/美股成交量已是股，不需要转换"""
    v = float(vol)
    if is_a_share(market):
        v *= 100
    return int(v)


def to_yahoo_symbol(code, market):
    """构造 Yahoo Finance 代码：港股补零+.HK，美股直接返回"""
    if is_hk(market):
        return str(int(code)).zfill(4) + '.HK'
    return str(code)


# ========================= 市场时间配置 =========================

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

def guess_market(code):
    """根据股票代码推断市场。
    0=深交所 (00xxxx, 30xxxx, 15xxxx, 16xxxx 等)
    1=上交所 (60xxxx, 68xxxx, 51xxxx, 56xxxx, 58xxxx, 50xxxx 等)
    2=北交所 (4xxxxx, 8xxxxx, 92xxxx)
    """
    c = str(code) if code else ''
    if not c: return '0'
    prefix2 = c[:2]
    prefix3 = c[:3]
    # 北交所: 40xxxx, 43xxxx, 83xxxx, 87xxxx, 92xxxx 等
    if c[0] in ('4', '8') or prefix2 == '92': return '2'
    # 上交所主板+科创板+沪ETF/LOF: 60xxxx, 68xxxx, 51xxxx, 56xxxx, 58xxxx, 50xxxx
    if c[0] == '6' or prefix2 in ('51', '56', '58', '50'):
        return '1'
    # 沪债: 11xxxx → 上交所
    if prefix2 == '11':
        return '1'
    # 深债: 12xxxx → 深交所
    if prefix2 == '12':
        return '0'
    # 其余归深交所: 00xxxx, 30xxxx, 15xxxx, 16xxxx, 18xxxx, 20xxxx 等
    return '0'


def to_em_market(market):
    """东方财富数据源将北交所（market=2）归为 market=0"""
    return '0' if str(market) == '2' else str(market)


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
        if is_a_share(market):
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


# ========================= 用户类型 =========================

# 用户类型枚举：0 普通用户 / 1 管理员 / 101 root
USER_TYPE_NORMAL = 0
USER_TYPE_ADMIN = 1
USER_TYPE_ROOT = 101

# 用户类型 -> 展示名称 映射
USER_TYPE_MAP = {
    USER_TYPE_NORMAL: '普通用户',
    USER_TYPE_ADMIN: '管理员',
    USER_TYPE_ROOT: 'root',
}


def get_usertype_name(user_type):
    """根据用户类型数字返回展示名称，未知类型返回空字符串"""
    return USER_TYPE_MAP.get(user_type, '')
