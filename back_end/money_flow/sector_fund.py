"""板块资金流向 — 东方财富行业/概念板块主力资金流入/流出排行"""

import requests
from common import REQUEST_PROXIES
from money_flow.storage import _EM_HEADERS, _EM_UT, _cached, db_set

_API_URL = "https://push2delay.eastmoney.com/api/qt/clist/get"
_FIELDS = "f2,f3,f4,f12,f14,f62,f184,f66,f72,f78,f84,f204,f205"
_PZ = 20  # 每次取 TOP20

# 板块类型 → fs 参数
_SECTOR_TYPES = {
    "industry": "m:90+t:2+f:!50",   # 行业板块
    "concept":  "m:90+t:3+f:!50",   # 概念板块
}

_SECTOR_FUND_KEY = "sector_fund"


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


def _fetch_sector_data(fs: str) -> dict:
    """请求东方财富板块资金数据，两次请求分别取流入/流出 TOP20"""
    # 流入 TOP20：po=1 按主力净流入降序
    inflow = _request_top(fs, po="1")
    # 流出 TOP20：po=0 按主力净流入升序（即净流出最大）
    outflow = _request_top(fs, po="0")
    return {"inflow": inflow, "outflow": outflow}


def _request_top(fs: str, po: str) -> list:
    """请求 API 返回 TOP20 列表"""
    params = {
        "pn": "1", "pz": str(_PZ), "po": po, "np": "1",
        "fltt": "2", "invt": "2",
        "fid": "f62",
        "fs": fs,
        "fields": _FIELDS,
        "ut": _EM_UT,
    }
    r = requests.get(_API_URL, params=params, headers=_EM_HEADERS, timeout=10, proxies=REQUEST_PROXIES)
    data = r.json()
    if not data.get("data") or not data["data"].get("diff"):
        return []

    result = []
    for item in data["data"]["diff"]:
        name = item.get("f14", "")
        if not name:
            continue
        main_net = item.get("f62")
        if main_net is None:
            continue

        change_pct = item.get("f3", 0)
        main_pct = item.get("f184", 0)
        super_net = item.get("f66")
        big_net = item.get("f72")
        mid_net = item.get("f78")
        small_net = item.get("f84")
        lead_stock = item.get("f204", "")
        lead_code = item.get("f205", "")
        sector_code = item.get("f12", "")

        row = {
            "name": name,
            "change_pct": f"{'+' if change_pct >= 0 else ''}{change_pct:.2f}%",
            "main_net": _format_amount(main_net),
            "main_pct": f"{'+' if main_pct >= 0 else ''}{main_pct:.2f}%",
            "super_net": _format_amount(super_net),
            "big_net": _format_amount(big_net),
            "mid_net": _format_amount(mid_net),
            "small_net": _format_amount(small_net),
            "lead_stock": lead_stock,
            "lead_code": lead_code,
            "sector_code": sector_code,
        }
        result.append(row)

    return result[:_PZ]


def get_sector_fund() -> dict:
    """获取行业+概念板块资金流入/流出排行"""
    cached = _cached(_SECTOR_FUND_KEY, ttl=30)
    if cached:
        return cached

    industry = _fetch_sector_data(_SECTOR_TYPES["industry"])
    concept = _fetch_sector_data(_SECTOR_TYPES["concept"])

    result = {
        "success": True,
        "industry": industry,
        "concept": concept,
    }
    db_set(_SECTOR_FUND_KEY, result, meta=str(int(__import__("time").time())))
    return result
