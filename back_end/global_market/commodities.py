"""全球大宗商品行情（东方财富 push2）"""
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from common import REQUEST_PROXIES, BROWSER_HEADERS

# 大宗商品配置：secid → 显示名称 + 价格除数
COMMODITIES = [
    {"secid": "122.XAU",  "name": "伦敦金现",   "divisor": 100,  "unit": "美元/盎司"},
    {"secid": "122.XAG",  "name": "伦敦银现",   "divisor": 100,  "unit": "美元/盎司"},
    {"secid": "102.CL00Y", "name": "轻质原油连续", "divisor": 100,  "unit": "美元/桶"},
    {"secid": "101.GC00Y", "name": "COMEX黄金",  "divisor": 10,   "unit": "美元/盎司"},
    {"secid": "101.SI00Y", "name": "COMEX白银",  "divisor": 2000, "unit": "美元/盎司"},
    {"secid": "101.HG00Y", "name": "COMEX铜",    "divisor": 100,  "unit": "美分/磅"},
    {"secid": "102.NG00Y", "name": "天然气连续",  "divisor": 1000, "unit": "美元/百万英热"},
]

EM_HEADERS = {
    **BROWSER_HEADERS,
    'Referer': 'https://quote.eastmoney.com/',
}


def _fetch_one(commodity: dict) -> dict:
    """抓取单个大宗商品行情"""
    secid = commodity["secid"]
    d = commodity["divisor"]
    url = "https://push2.eastmoney.com/api/qt/stock/get"
    params = {
        "secid": secid,
        "fields": "f43,f57,f58,f60,f169,f170,f171",
    }
    r = requests.get(url, params=params, headers=EM_HEADERS,
                     timeout=8, proxies=REQUEST_PROXIES)
    data = r.json()
    if data.get("rc") != 0 or not data.get("data"):
        return {"name": commodity["name"], "price": "-", "change": "-",
                "change_pct": "-", "unit": commodity["unit"], "error": "无数据"}

    drow = data["data"]
    def raw(key):
        try:
            return float(drow.get(key, 0))
        except (ValueError, TypeError):
            return 0.0

    price = raw("f43") / d
    prev = raw("f60") / d
    change = price - prev
    change_pct = 0.0
    if prev != 0:
        change_pct = change / prev * 100

    # 价格小数位
    if price >= 100:
        price_fmt = f"{price:.1f}"
    elif price >= 1:
        price_fmt = f"{price:.2f}"
    else:
        price_fmt = f"{price:.3f}"

    return {
        "name": commodity["name"],
        "code": drow.get("f57", "-"),
        "price": price_fmt,
        "change": f"{change:+.2f}",
        "change_pct": f"{change_pct:+.2f}%",
        "unit": commodity["unit"],
    }


def get_global_commodities() -> dict:
    """并行获取所有大宗商品行情"""
    result = {"success": True, "data": []}
    try:
        with ThreadPoolExecutor(max_workers=len(COMMODITIES)) as executor:
            futures = {executor.submit(_fetch_one, c): c for c in COMMODITIES}
            for future in as_completed(futures):
                r = future.result()
                if r:
                    result["data"].append(r)
    except Exception as e:
        result["success"] = False
        result["error"] = str(e)

    # 保持配置顺序
    name_order = {c["name"]: i for i, c in enumerate(COMMODITIES)}
    result["data"].sort(key=lambda x: name_order.get(x["name"], 99))
    return result
