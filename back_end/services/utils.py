"""通用格式化函数"""

def is_etf(code, market):
    """判断是否为ETF（沪市51xxxx，深市15xxxx）"""
    c = str(code) if code else ''
    m = str(market) if market else ''
    if m in ('1', '2') and c[:2] == '51':
        return True
    if m == '0' and c[:2] == '15':
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
