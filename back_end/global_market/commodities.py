"""全球大宗商品行情（东方财富 push2 ulist 批量接口）"""
import requests
from common import REQUEST_PROXIES, BROWSER_HEADERS

COMMODITIES = [
    # 按品种分组：金→银→铜，每组伦敦→COMEX→沪
    {"secid": "122.XAU",  "name": "伦敦金现",   "divisor": 100,  "unit": "美元/盎司"},
    {"secid": "101.GC00Y", "name": "COMEX黄金",  "divisor": 10,   "unit": "美元/盎司"},
    {"secid": "113.aum",   "name": "沪金主连",   "divisor": 100,  "unit": "元/克"},
    {"secid": "122.XAG",  "name": "伦敦银现",   "divisor": 100,  "unit": "美元/盎司"},
    {"secid": "101.SI00Y", "name": "COMEX白银",  "divisor": 2000, "unit": "美元/盎司"},
    {"secid": "113.agm",   "name": "沪银主连",   "divisor": 1,    "unit": "元/千克"},
    {"secid": "109.LCPT", "name": "伦敦铜",     "divisor": 100,  "unit": "美元/吨"},
    {"secid": "101.HG00Y", "name": "COMEX铜",    "divisor": 100,  "unit": "美分/磅"},
    {"secid": "113.cum",   "name": "沪铜主连",   "divisor": 1,    "unit": "元/吨"},
]

ULIST_HEADERS = {
    **BROWSER_HEADERS,
    'Referer': 'https://quote.eastmoney.com/',
}


def get_global_commodities() -> dict:
    """批量获取所有大宗商品行情（单次请求）"""
    secids = ",".join(c["secid"] for c in COMMODITIES)
    url = "https://push2.eastmoney.com/api/qt/ulist.np/get"
    params = {
        "secids": secids,
        "fields": "f2,f3,f4,f12,f14,f18",
    }
    r = requests.get(url, params=params, headers=ULIST_HEADERS,
                     timeout=10, proxies=REQUEST_PROXIES)
    data = r.json()
    if data.get("rc") != 0:
        return {"success": False, "data": [], "error": f"API error rc={data.get('rc')}"}

    diff = data.get("data", {}).get("diff", [])
    if not diff:
        return {"success": False, "data": [], "error": "无数据"}

    secid_order = {c["secid"].split(".")[-1]: i for i, c in enumerate(COMMODITIES)}
    result = {"success": True, "data": []}

    for i, item in enumerate(diff):
        code = item.get("f12", "-")
        # diff 顺序与 secids 顺序一致
        cfg = COMMODITIES[i]
        d = cfg["divisor"]

        def raw(key):
            try:
                return float(item.get(key, 0))
            except (ValueError, TypeError):
                return 0.0

        price = raw("f2") / d
        prev = raw("f18") / d
        change = price - prev
        change_pct = change / prev * 100 if prev != 0 else 0.0

        if price >= 100:
            price_fmt = f"{price:.1f}"
        elif price >= 1:
            price_fmt = f"{price:.2f}"
        else:
            price_fmt = f"{price:.3f}"

        result["data"].append({
            "name": cfg["name"],
            "code": code,
            "price": price_fmt,
            "change": f"{change:+.2f}",
            "change_pct": f"{change_pct:+.2f}%",
            "unit": cfg["unit"],
        })

    return result
