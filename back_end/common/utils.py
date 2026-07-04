"""通用格式化函数"""

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
