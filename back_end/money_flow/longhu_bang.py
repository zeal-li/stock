"""龙虎榜数据（东方财富数据中心）"""
import datetime
import requests
from common import REQUEST_PROXIES


def _fetch_longhu_bang(trade_date: str = None):
    """从东方财富数据中心获取龙虎榜每日明细"""
    if not trade_date:
        trade_date = datetime.date.today().strftime("%Y-%m-%d")

    url = "https://datacenter-web.eastmoney.com/api/data/v1/get"
    params = {
        "reportName": "RPT_ORGANIZATION_TRADE_DETAILSNEW",
        "columns": "ALL",
        "filter": f"(TRADE_DATE='{trade_date}')",
        "sortColumns": "NET_BUY_AMT",
        "sortTypes": "-1",
        "pageSize": 200,
        "pageNumber": 1,
        "source": "WEB",
        "client": "WEB",
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Referer": "https://data.eastmoney.com/stock/lhb.html",
    }

    r = requests.get(url, params=params, headers=headers, timeout=15, proxies=REQUEST_PROXIES)
    data = r.json()

    if not data.get("success"):
        return {"success": False, "error": f"龙虎榜数据请求失败: {data.get('message', '')}"}

    items = (data.get("result") or {}).get("data") or []
    if not items:
        return {"success": True, "data": {"trade_date": trade_date, "list": []}}

    result = []
    for item in items:
        result.append({
            "code": str(item.get("SECURITY_CODE", "")),
            "name": str(item.get("SECURITY_NAME_ABBR", "")),
            "price": item.get("CLOSE_PRICE"),
            "change_pct": item.get("CHANGE_RATE"),
            "turnover_rate": item.get("TURNOVERRATE"),
            "net_amt": item.get("NET_BUY_AMT"),
            "buy_amt": item.get("BUY_AMT"),
            "sell_amt": item.get("SELL_AMT"),
            "total_amt": item.get("ACCUM_AMOUNT"),
            "reason": str(item.get("EXPLANATION", "")),
            "buy_seat_count": item.get("BUY_TIMES"),
            "sell_seat_count": item.get("SELL_TIMES"),
            "market": str(item.get("MARKET", "")),
            "free_cap": item.get("FREECAP"),
            "ratio": item.get("RATIO"),
            "trade_date": str(item.get("TRADE_DATE", ""))[:10],
            # 上榜后表现
            "d1_return": item.get("D1_CLOSE_ADJCHRATE"),
            "d2_return": item.get("D2_CLOSE_ADJCHRATE"),
            "d3_return": item.get("D3_CLOSE_ADJCHRATE"),
            "d5_return": item.get("D5_CLOSE_ADJCHRATE"),
            "d10_return": item.get("D10_CLOSE_ADJCHRATE"),
        })

    return {"success": True, "data": {"trade_date": trade_date, "list": result}}


def get_longhu_bang(trade_date: str = None):
    """获取龙虎榜数据"""
    return _fetch_longhu_bang(trade_date)
