"""全球大宗商品行情（新浪财经 hq.sinajs.cn）"""
import requests
from common import BROWSER_HEADERS

COMMODITIES = [
    # 第一行：金属 — 金银铜铝，每组伦敦→COMEX→沪，铝接在铜后
    {"code": "hf_XAU",  "name": "伦敦金现",   "unit": "美元/盎司", "source": "spot"},
    {"code": "hf_GC",   "name": "COMEX黄金",  "unit": "美元/盎司", "source": "futures"},
    {"code": "nf_AU0",  "name": "沪金主连",   "unit": "元/克",     "source": "nf"},
    {"code": "hf_XAG",  "name": "伦敦银现",   "unit": "美元/盎司", "source": "spot"},
    {"code": "hf_SI",   "name": "COMEX白银",  "unit": "美元/盎司", "source": "futures"},
    {"code": "nf_AG0",  "name": "沪银主连",   "unit": "元/千克",   "source": "nf"},
    {"code": "hf_CAD",  "name": "伦敦铜",     "unit": "美元/吨",   "source": "futures"},
    {"code": "hf_HG",   "name": "COMEX铜",    "unit": "美分/磅",   "source": "futures"},
    {"code": "nf_CU0",  "name": "沪铜主连",   "unit": "元/吨",     "source": "nf"},
    {"code": "hf_AHD",  "name": "伦铝",       "unit": "美元/吨",   "source": "futures"},
    {"code": "nf_AL0",  "name": "沪铝主连",   "unit": "元/吨",     "source": "nf"},
    {"code": None,       "name": "",           "unit": "",           "source": "gap"},
    # 第二行：能源 + 煤炭
    {"code": "hf_OIL",  "name": "布伦特原油", "unit": "美元/桶",   "source": "futures"},
    {"code": "hf_CL",   "name": "WTI原油",    "unit": "美元/桶",   "source": "futures"},
    {"code": "hf_GAS",  "name": "柴油主连",   "unit": "美元/吨",   "source": "futures"},
    {"code": "hf_HO",   "name": "取暖油主连", "unit": "美元/加仑", "source": "futures"},
    {"code": "hf_NG",   "name": "天然气主连", "unit": "美元/百万英热", "source": "futures"},
    {"code": "nf_JM0",  "name": "焦煤主连",   "unit": "元/吨",     "source": "nf"},
    {"code": "nf_J0",   "name": "焦炭主连",   "unit": "元/吨",     "source": "nf"},
    {"code": None,       "name": "",           "unit": "",           "source": "gap"},
    {"code": None,       "name": "",           "unit": "",           "source": "gap"},
    {"code": None,       "name": "",           "unit": "",           "source": "gap"},
    {"code": None,       "name": "",           "unit": "",           "source": "gap"},
    {"code": None,       "name": "",           "unit": "",           "source": "gap"},
    # 第三行：国际农产品 — 大豆链→谷物链→软商品
    {"code": "hf_S",    "name": "美大豆",     "unit": "美分/蒲式耳", "source": "futures"},
    {"code": "hf_SM",   "name": "美豆粕",     "unit": "美元/短吨",   "source": "futures"},
    {"code": "hf_BO",   "name": "美豆油",     "unit": "美分/磅",     "source": "futures"},
    {"code": "hf_W",    "name": "美小麦",     "unit": "美分/蒲式耳", "source": "futures"},
    {"code": "hf_C",    "name": "美玉米",     "unit": "美分/蒲式耳", "source": "futures"},
    {"code": "hf_CT",   "name": "美棉花",     "unit": "美分/磅",     "source": "futures"},
    {"code": "hf_CC",   "name": "可可",       "unit": "美元/吨",     "source": "futures"},
    {"code": None,       "name": "",           "unit": "",            "source": "gap"},
    {"code": None,       "name": "",           "unit": "",            "source": "gap"},
    {"code": None,       "name": "",           "unit": "",            "source": "gap"},
    {"code": None,       "name": "",           "unit": "",            "source": "gap"},
    {"code": None,       "name": "",           "unit": "",            "source": "gap"},
    # 第四行：国内农产品 — 油料谷物
    {"code": "nf_M0",   "name": "豆粕主连",   "unit": "元/吨",     "source": "nf"},
    {"code": "nf_A0",   "name": "豆一主连",   "unit": "元/吨",     "source": "nf"},
    {"code": "nf_Y0",   "name": "豆油主连",   "unit": "元/吨",     "source": "nf"},
    {"code": "nf_P0",   "name": "棕榈油主连", "unit": "元/吨",     "source": "nf"},
    {"code": "nf_C0",   "name": "玉米主连",   "unit": "元/吨",     "source": "nf"},
    {"code": "nf_CF0",  "name": "棉花主连",   "unit": "元/吨",     "source": "nf"},
    {"code": "nf_RM0",  "name": "菜粕主连",   "unit": "元/吨",     "source": "nf"},
    {"code": "nf_SR0",  "name": "白糖主连",   "unit": "元/吨",     "source": "nf"},
    {"code": None,       "name": "",           "unit": "",           "source": "gap"},
    {"code": None,       "name": "",           "unit": "",           "source": "gap"},
    {"code": None,       "name": "",           "unit": "",           "source": "gap"},
    {"code": None,       "name": "",           "unit": "",           "source": "gap"},
    # 第五行：国内农产品 — 畜牧园艺
    {"code": "nf_JD0",  "name": "鸡蛋主连",   "unit": "元/500kg",  "source": "nf"},
    {"code": "nf_LH0",  "name": "生猪主连",   "unit": "元/吨",     "source": "nf"},
    {"code": "nf_AP0",  "name": "苹果主连",   "unit": "元/吨",     "source": "nf"},
    {"code": "nf_PK0",  "name": "花生主连",   "unit": "元/吨",     "source": "nf"},
    {"code": None,       "name": "",           "unit": "",           "source": "gap"},
    {"code": None,       "name": "",           "unit": "",           "source": "gap"},
    {"code": None,       "name": "",           "unit": "",           "source": "gap"},
    {"code": None,       "name": "",           "unit": "",           "source": "gap"},
    {"code": None,       "name": "",           "unit": "",           "source": "gap"},
    {"code": None,       "name": "",           "unit": "",           "source": "gap"},
    {"code": None,       "name": "",           "unit": "",           "source": "gap"},
    {"code": None,       "name": "",           "unit": "",           "source": "gap"},
]

SINA_HEADERS = {
    **BROWSER_HEADERS,
    'Referer': 'https://finance.sina.com.cn',
}


def _parse_hf(item: str, cfg: dict) -> dict:
    """解析 hf_ 国际期货/现货数据
    字段: 0最新价, 1昨收(spot非空)/空(futures), 2今开, 3最高价, 4最低价, ...
         7参考价(昨收/昨结), 12日期, 13名称
    """
    parts = item.split(",")
    price = float(parts[0])
    # spot: 昨收在字段1; futures: 昨结在字段7
    if parts[1]:
        prev = float(parts[1])
    else:
        prev = float(parts[7])
    change = price - prev
    change_pct = change / prev * 100 if prev != 0 else 0.0

    if price >= 100:
        price_fmt = f"{price:.1f}"
    elif price >= 1:
        price_fmt = f"{price:.2f}"
    else:
        price_fmt = f"{price:.3f}"

    return {
        "name": cfg["name"],
        "code": "—",
        "price": price_fmt,
        "change": f"{change:+.2f}",
        "change_pct": f"{change_pct:+.2f}%",
        "unit": cfg["unit"],
    }


def _parse_nf(item: str, cfg: dict) -> dict:
    """解析 nf_ 国内期货连续合约数据
    字段: 0名称, 1市场代码, 2今开, 3最高, 4最低, 5结算价, 6买一价, 7卖一价,
         8最新价, 9-, 10昨结算, 11买量, 12卖量, 13持仓量, 14成交量, 15市场, 16品种, 17日期
    """
    parts = item.split(",")
    price = float(parts[8])
    prev = float(parts[10])
    change = price - prev
    change_pct = change / prev * 100 if prev != 0 else 0.0

    if price >= 100000:
        price_fmt = f"{price:.0f}"
    elif price >= 100:
        price_fmt = f"{price:.1f}"
    elif price >= 1:
        price_fmt = f"{price:.2f}"
    else:
        price_fmt = f"{price:.3f}"

    return {
        "name": cfg["name"],
        "code": "—",
        "price": price_fmt,
        "change": f"{change:+.2f}",
        "change_pct": f"{change_pct:+.2f}%",
        "unit": cfg["unit"],
    }


def get_global_commodities() -> dict:
    """批量获取所有大宗商品行情（单次请求）"""
    real_items = [c for c in COMMODITIES if c["source"] != "gap"]
    codes = ",".join(c["code"] for c in real_items)
    url = "https://hq.sinajs.cn/list=" + codes
    r = requests.get(url, headers=SINA_HEADERS, timeout=10)
    r.encoding = "gb2312"

    raw_lines = r.text.strip().split("\n")
    if len(raw_lines) != len(real_items):
        return {"success": False, "data": [], "error": f"响应行数不匹配: {len(raw_lines)} vs {len(real_items)}"}

    result = {"success": True, "data": []}
    real_idx = 0

    for i, cfg in enumerate(COMMODITIES):
        if cfg["source"] == "gap":
            result["data"].append({"name": "", "price": "", "change": "", "change_pct": "", "unit": "", "gap": True})
            continue
        data_str = raw_lines[real_idx].split('"')[1]
        real_idx += 1
        if not data_str.strip():
            return {"success": False, "data": [], "error": f"{cfg['name']} 无数据"}

        if cfg["source"] == "nf":
            result["data"].append(_parse_nf(data_str, cfg))
        else:
            result["data"].append(_parse_hf(data_str, cfg))

    return result
