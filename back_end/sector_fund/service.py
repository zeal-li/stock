"""板块资金流向 — 东方财富行业/概念板块主力资金流入/流出排行"""

import re
import time
import requests
from common import REQUEST_PROXIES
from common.utils import is_etf, fmt, fmt_pct, fmt_volume, fmt_amount, fmt_cap
from money_flow.storage import _EM_HEADERS, _EM_UT
from sector_fund.storage import cache_get, cache_set

_API_URL = "https://push2delay.eastmoney.com/api/qt/clist/get"
_FIELDS = "f2,f3,f4,f12,f14,f62,f66,f72,f78,f84,f164,f174,f204,f205"
_STOCK_FIELDS = "f2,f3,f4,f5,f6,f7,f8,f12,f13,f14,f15,f16,f17,f18,f20,f21,f62,f184"
_PZ = 30
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


def _safe_float(val):
    """安全转换为 float，处理 '-'（停牌/无数据）"""
    if val is None or val == "-":
        return None
    return float(val)


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

        change_pct = _safe_float(item.get("f3", 0))
        price = _safe_float(item.get("f2", 0))
        change_amt = _safe_float(item.get("f4", 0))
        volume = _safe_float(item.get("f5", 0))
        amount = _safe_float(item.get("f6", 0))
        amplitude = _safe_float(item.get("f7", 0))
        turnover = _safe_float(item.get("f8", 0))
        main_net = item.get("f62")

        stocks.append({
            "name": name,
            "code": code,
            "market": str(market),
            "change_pct": f"{'+' if (change_pct or 0) >= 0 else ''}{(change_pct if change_pct is not None else 0):.2f}%" if change_pct is not None else "-",
            "price": round(price, 2) if price is not None else "-",
            "change_amt": round(change_amt, 2) if change_amt is not None else "-",
            "volume": volume if volume is not None else "-",
            "amount": amount if amount is not None else "-",
            "amplitude": f"{amplitude:.2f}%" if amplitude is not None else "-",
            "turnover": f"{turnover:.2f}%" if turnover is not None else "-",
            "main_net": _format_amount(main_net),
        })

    return {"success": True, "stocks": stocks, "total": total}


def _parse_fundf10_holdings(code: str, topline: int = 300, year: str = "") -> list:
    """从 fundf10 jjcc API 解析 ETF 持仓股票列表，返回 [{code, market, name, ratio}]"""
    params = {
        "type": "jjcc",
        "code": code,
        "topline": str(topline),
        "year": year,
        "month": "",
        "rt": "0.5",
    }
    r = requests.get("https://fundf10.eastmoney.com/FundArchivesDatas.aspx",
                      params=params,
                      headers={"User-Agent": "Mozilla/5.0", "Referer": "https://fund.eastmoney.com/"},
                      timeout=15, proxies=REQUEST_PROXIES)
    if r.status_code != 200:
        return []

    text = r.text
    # 按季度分组，取第一个有数据的季度（即最新）
    sections = text.split("<div class='box'>")
    for section in sections[1:]:
        # 按行整体提取：代码、名称、占比 — 避免全局扫描 tor td 导致索引错位
        row_pattern = (
            r"<tr><td>\d+</td>"
            r"<td><a[^>]*>(\d{6})</a></td>"
            r"<td[^>]*><a[^>]*>([^<]+)</a></td>"
            r"[\s\S]*?"
            r"<td[^>]*class=['\"]tor['\"]>([^<]*%)</td>"
            r"[\s\S]*?</tr>"
        )
        rows = re.findall(row_pattern, section)
        if not rows:
            continue

        stocks = []
        for row in rows:
            stock_code = row[0]
            if stock_code.startswith(("6", "9")):
                market = "1"
            else:
                market = "0"
            stocks.append({
                "code": stock_code,
                "market": market,
                "name": row[1].strip(),
                "ratio": row[2].strip(),
            })
        return stocks

    return []


def get_etf_stocks(code: str, market: str) -> dict:
    """获取ETF成分股列表（前端按占比排序）
    步骤：1) 从 fundf10 解析持仓股票代码  2) 用 ulist.np/get 获取实时行情
    """
    if not code or not market:
        return {"success": False, "error": "缺少参数"}

    # 从 fundf10 解析持仓，优先取数据最多的年份（覆盖面更全）
    from datetime import datetime as _dt
    cur_year = str(_dt.now().year)
    prev_year = str(_dt.now().year - 1)
    holdings_cur = _parse_fundf10_holdings(code, topline=300, year=cur_year)
    holdings_prev = _parse_fundf10_holdings(code, topline=300, year=prev_year)
    holdings = holdings_cur if len(holdings_cur) >= len(holdings_prev) else holdings_prev
    if not holdings:
        # 再试不指定年份（让 API 自行选择）
        holdings = _parse_fundf10_holdings(code, topline=300, year="")
    if not holdings:
        return {"success": True, "stocks": [], "total": 0}

    total = len(holdings)

    # 构造 secids，调用 ulist.np/get 获取实时行情
    secids = ",".join(f"{s['market']}.{s['code']}" for s in holdings)
    url = "https://push2delay.eastmoney.com/api/qt/ulist.np/get"
    params = {
        "fltt": "2", "invt": "2",
        "fields": "f2,f3,f4,f5,f6,f7,f8,f12,f13,f14,f62",
        "secids": secids,
        "ut": _EM_UT,
    }
    r = requests.get(url, params=params, headers=_EM_HEADERS, timeout=10, proxies=REQUEST_PROXIES)
    quote_data = {}
    try:
        diff = (r.json().get("data") or {}).get("diff") or []
        for row in diff:
            key = f"{row.get('f13', '')}.{row.get('f12', '')}"
            if row.get("f12"):
                quote_data[key] = row
    except Exception:
        pass

    # 合合持仓 + 行情，按涨跌幅排序
    stocks = []
    for h in holdings:
        key = f"{h['market']}.{h['code']}"
        q = quote_data.get(key)

        change_pct = _safe_float(q.get("f3", 0)) if q else None
        price = _safe_float(q.get("f2", 0)) if q else None
        change_amt = _safe_float(q.get("f4", 0)) if q else None
        turnover = _safe_float(q.get("f8", 0)) if q else None
        amplitude = _safe_float(q.get("f7", 0)) if q else None
        main_net = q.get("f62") if q else None
        name = (q.get("f14") or h["name"]) if q else h["name"]

        etf = is_etf(h["code"], h["market"])

        stocks.append({
            "name": name,
            "code": h["code"],
            "market": h["market"],
            "change_pct": f"{'+' if (change_pct or 0) >= 0 else ''}{(change_pct if change_pct is not None else 0):.2f}%" if change_pct is not None else "-",
            "price": fmt(price, etf) if price is not None else "-",
            "change_amt": fmt(change_amt, etf) if change_amt is not None else "-",
            "turnover": f"{turnover:.2f}%" if turnover is not None else "-",
            "amplitude": f"{amplitude:.2f}%" if amplitude is not None else "-",
            "main_net": _format_amount(main_net),
            "ratio": h["ratio"],
        })

    # 排序由前端完成
    return {"success": True, "stocks": stocks, "total": total}
