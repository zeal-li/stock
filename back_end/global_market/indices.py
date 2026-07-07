"""全球指数实时行情 - 统一新浪财经 hq.sinajs.cn"""

import requests
from common import BROWSER_HEADERS

_SINA_HEADERS = {
    **BROWSER_HEADERS,
    'Referer': 'https://finance.sina.com.cn',
}

# A股指数：名称, 新浪代码（第一排）
A_INDEX_LIST = [
    ('上证指数', 's_sh000001'),
    ('深证成指', 's_sz399001'),
    ('创业板指', 's_sz399006'),
    ('科创50',   's_sh000688'),
    ('沪深300',  's_sh000300'),
    ('中证500',  's_sh000905'),
    ('中证1000', 's_sh000852'),
    ('上证50',   's_sh000016'),
]

# 海外指数：名称, 新浪代码（第二排）
# 道琼斯/纳斯达克用 gb_ 实时代码（int_ 是静态快照，数据不更新）
US_INDEX_LIST = [
    ('道琼斯',   'gb_$dji'),
    ('纳斯达克', 'gb_$ixic'),
    ('英国富时', 'znb_UKX'),
    ('德国DAX',  'znb_DAX'),
    ('法国CAC',  'znb_CAC'),
    ('日经225',  'znb_NKY'),
    ('韩国KOSPI','znb_KOSPI'),
]

# znb_ 前缀代码 → globalindex 页面代码映射
_ZNB_TO_GLOBAL = {
    'znb_UKX':   'UKX',
    'znb_DAX':   'DAX',
    'znb_CAC':   'CAC',
    'znb_NKY':   'NKY',
    'znb_KOSPI': 'KOSPI',
}

# gb_ 前缀代码 → usstock 代码映射
_GB_TO_US = {
    'gb_$dji':  '.dji',
    'gb_$ixic': '.ixic',
}


def _make_index_url(code: str) -> str:
    # A股指数：s_ 前缀 → realstock/company/{code_without_s_}/nc.shtml
    if code.startswith('s_'):
        real_code = code[2:]  # 去掉 s_ 前缀
        return f"https://finance.sina.com.cn/realstock/company/{real_code}/nc.shtml"

    # 美股指数：gb_ / int_ 前缀 → usstock/quotes/{code}.html
    us_code = _GB_TO_US.get(code)
    if us_code:
        return f"https://stock.finance.sina.com.cn/usstock/quotes/{us_code}.html"

    # 国际指数：znb_ 前缀 → stock/globalindex/quotes/{code}
    global_code = _ZNB_TO_GLOBAL.get(code)
    if global_code:
        return f"https://finance.sina.com.cn/stock/globalindex/quotes/{global_code}"

    # 兜底（理论上不会走到这里）
    return f"https://finance.sina.com.cn/realstock/company/{code}/nc.shtml"


def get_global_indices():
    """返回 12 列扁平列表，A股第一排 + 空格 + 美股第二排"""
    try:
        all_codes = [code for _, code in A_INDEX_LIST] + [code for _, code in US_INDEX_LIST]
        url = "https://hq.sinajs.cn/list=" + ','.join(all_codes)
        r = requests.get(url, headers=_SINA_HEADERS, timeout=10)
        r.encoding = "gb2312"

        parsed = {}
        for line in r.text.strip().split("\n"):
            if '=""' in line or '="' not in line:
                continue
            code = line.split('var hq_str_')[1].split('="')[0]
            payload = line.split('="')[1].rstrip('";')
            parts = payload.split(',')
            if len(parts) < 4:
                continue

            name = parts[0].strip()
            price = float(parts[1]) if parts[1] else 0
            # gb_ 代码字段顺序不同：price(1), change_pct(2), change_value(4)
            is_gb = code.startswith('gb_')
            if is_gb:
                chg_pct = float(parts[2]) if parts[2] else 0
                chg_val = float(parts[4]) if len(parts) > 4 and parts[4] else 0
            else:
                chg_val = float(parts[2]) if parts[2] else 0
                chg_pct = float(parts[3]) if parts[3] else 0

            parsed[code] = {
                'name': name,
                'price': f"{price:.2f}",
                'change': f"{'+' if chg_pct >= 0 else ''}{chg_pct:.2f}%",
                'change_value': f"{'+' if chg_val >= 0 else ''}{chg_val:.2f}",
                'url': _make_index_url(code),
            }

        a_data = [parsed[code] for _, code in A_INDEX_LIST if code in parsed]
        us_data = [parsed[code] for _, code in US_INDEX_LIST if code in parsed]

        # 按实际数量动态补空格，每排填满 12 列
        result = a_data + [{'gap': True}] * (12 - len(a_data))
        result += us_data + [{'gap': True}] * (12 - len(us_data))
        return {'success': True, 'data': result}
    except Exception as e:
        return {'success': False, 'error': str(e)}
