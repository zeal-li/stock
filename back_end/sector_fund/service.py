"""板块资金流向 — 东方财富行业/概念板块主力资金流入/流出排行"""

import time
import requests
from common import REQUEST_PROXIES
from money_flow.storage import _EM_HEADERS, _EM_UT
from sector_fund.storage import cache_get, cache_set

_API_URL = "https://push2delay.eastmoney.com/api/qt/clist/get"
_FIELDS = "f2,f3,f4,f12,f14,f62,f66,f72,f78,f84,f164,f174,f204,f205"
_STOCK_FIELDS = "f2,f3,f4,f5,f6,f7,f8,f12,f13,f14,f15,f16,f17,f18,f20,f21,f62,f184"
_PZ = 20
_CACHE_TTL = 60

_SECTOR_TYPES = {
    "industry": "m:90+t:2+f:!50",
    "concept":  "m:90+t:3+f:!50",
}

_PERIOD_CONFIG = {
    "today": {"fid": "f62", "field": "f62"},
    "5d":    {"fid": "f164", "field": "f164"},
    "10d":   {"fid": "f174", "field": "f174"},
}


def _format_amount(val) -> str:
    """金额格式化：元 → 亿元/万元"""
    if val is None or val == "-":
        return "-"
    abs_val = abs(val)
    sign = "+" if val >= 0 else "-"
    if abs_val >= 1e8:
        return f"{sign}{abs_val / 1e8:.2f}亿"
    elif abs_val >= 1e4:
        return f"{sign}{abs_val / 1e4:.2f}万"
    else:
        return f"{sign}{abs_val:.0f}元"


def _request_top(fs: str, period: str, po: str) -> list:
    cfg = _PERIOD_CONFIG.get(period, _PERIOD_CONFIG["today"])
    params = {
        "pn": "1", "pz": str(_PZ), "po": po, "np": "1",
        "fltt": "2", "invt": "2",
        "fid": cfg["fid"],
        "fs": fs,
        "fields": _FIELDS,
        "ut": _EM_UT,
    }
    r = requests.get(_API_URL, params=params, headers=_EM_HEADERS, timeout=10, proxies=REQUEST_PROXIES)
    data = r.json()
    if not data.get("data") or not data["data"].get("diff"):
        return []

    result = []
    main_field = cfg["field"]
    for item in data["data"]["diff"]:
        name = item.get("f14", "")
        if not name:
            continue
        main_net = item.get(main_field)
        if main_net is None:
            continue

        change_pct = item.get("f3", 0)
        super_net = item.get("f66")
        big_net = item.get("f72")
        mid_net = item.get("f78")
        small_net = item.get("f84")
        lead_stock = item.get("f204", "")
        lead_code = item.get("f205", "")
        sector_code = item.get("f12", "")

        result.append({
            "name": name,
            "change_pct": f"{'+' if change_pct >= 0 else ''}{change_pct:.2f}%",
            "main_net": _format_amount(main_net),
            "super_net": _format_amount(super_net),
            "big_net": _format_amount(big_net),
            "mid_net": _format_amount(mid_net),
            "small_net": _format_amount(small_net),
            "lead_stock": lead_stock,
            "lead_code": lead_code,
            "sector_code": sector_code,
        })

    return result[:_PZ]


def _make_key(sector_type: str, period: str, top: str) -> str:
    return f"{sector_type}_{period}_{top}"


def _fetch_and_cache(fs: str, sector_type: str, period: str) -> dict:
    """请求东方财富 API，存储 inflow+outflow 到 DB，返回两个列表"""
    inflow = _request_top(fs, period, po="1")
    outflow = _request_top(fs, period, po="0")

    cache_set(_make_key(sector_type, period, "inflow"), inflow)
    cache_set(_make_key(sector_type, period, "outflow"), outflow)

    return {"inflow": inflow, "outflow": outflow}


def get_sector_fund(sector_type: str = "concept", period: str = "today") -> dict:
    """获取指定板块类型+时间段的资金流向排行（带 10s 缓存）"""
    if sector_type not in _SECTOR_TYPES:
        return {"success": False, "error": f"未知板块类型: {sector_type}"}
    if period not in _PERIOD_CONFIG:
        return {"success": False, "error": f"未知时间段: {period}"}

    inflow_key = _make_key(sector_type, period, "inflow")
    outflow_key = _make_key(sector_type, period, "outflow")

    # 两个 key 都在缓存中 → 直接返回
    inflow_cached = cache_get(inflow_key)
    outflow_cached = cache_get(outflow_key)
    if inflow_cached and outflow_cached:
        t_inflow = time.time() - inflow_cached[1]
        t_outflow = time.time() - outflow_cached[1]
        if t_inflow < _CACHE_TTL and t_outflow < _CACHE_TTL:
            return {
                "success": True,
                "inflow": inflow_cached[0],
                "outflow": outflow_cached[0],
            }

    # 缓存过期或不存在 → 请求 API 并缓存
    fs = _SECTOR_TYPES[sector_type]
    data = _fetch_and_cache(fs, sector_type, period)
    return {
        "success": True,
        "inflow": data["inflow"],
        "outflow": data["outflow"],
    }


def get_sector_stocks(sector_code: str) -> dict:
    """获取板块成分股列表（按涨跌幅排序）"""
    if not sector_code:
        return {"success": False, "error": "缺少板块编码"}

    params = {
        "pn": "1", "pz": "100", "po": "1", "np": "1",
        "fltt": "2", "invt": "2",
        "fid": "f3",
        "fs": f"b:{sector_code}",
        "fields": _STOCK_FIELDS,
        "ut": _EM_UT,
    }
    r = requests.get(_API_URL, params=params, headers=_EM_HEADERS, timeout=10, proxies=REQUEST_PROXIES)
    data = r.json()
    if not data.get("data") or not data["data"].get("diff"):
        return {"success": True, "stocks": [], "total": 0}

    total = data["data"].get("total", 0)
    stocks = []
    for item in data["data"]["diff"]:
        name = item.get("f14", "")
        code = item.get("f12", "")
        market = item.get("f13", "")
        if not name or not code:
            continue

        change_pct = float(item.get("f3", 0))
        price = item.get("f2", 0)
        change_amt = item.get("f4", 0)
        volume = item.get("f5", 0)
        amount = item.get("f6", 0)
        amplitude = item.get("f7", 0)
        turnover = item.get("f8", 0)
        main_net = item.get("f62")

        stocks.append({
            "name": name,
            "code": code,
            "market": str(market),
            "change_pct": f"{'+' if change_pct >= 0 else ''}{change_pct:.2f}%",
            "price": round(float(price), 2) if price else "-",
            "change_amt": round(float(change_amt), 2) if change_amt else "-",
            "volume": volume,
            "amount": amount,
            "amplitude": f"{float(amplitude):.2f}%" if amplitude else "-",
            "turnover": f"{float(turnover):.2f}%" if turnover else "-",
            "main_net": _format_amount(main_net),
        })

    return {"success": True, "stocks": stocks, "total": total}
