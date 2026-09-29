"""板块资金流向 — 东方财富行业/概念板块主力资金流入/流出排行（按交易日持久化）"""

import datetime
import re
import threading
import time

from bs4 import BeautifulSoup

from common.browser import jsonp_get
from common.http import get_text, get_realtime_quotes_gtimg, get_sina_hq
from common.utils import is_etf, fmt, is_a_share, is_hk, is_us, is_a_share_trading_day, is_market_opened, get_market_hours
from sector_fund.storage import rank_get, rank_set, form_get, form_set, cleanup_old_data

_API_URL = "https://push2.eastmoney.com/api/qt/clist/get"
# 东财板块资金接口 token（从网页 bkzj/list.js 提取，旧 token bd1d... 已失效）
_EM_BKZJ_UT = "8dec03ba335b81bf4ebdf7b29ec27d15"
_FIELDS = "f2,f3,f4,f12,f14,f62,f66,f72,f78,f84,f164,f174,f204,f205"
_STOCK_FIELDS = "f2,f3,f4,f5,f6,f7,f8,f12,f13,f14,f15,f16,f17,f18,f20,f21,f62,f184"
_PZ = 50

_SECTOR_TYPES = {
    "industry": "m:90+t:2+f:!50",
    "concept":  "m:90+t:3+f:!50",
}

_PERIOD_CONFIG = {
    "today": {"fid": "f62", "field": "f62"},
    "5d":    {"fid": "f164", "field": "f164"},
    "10d":   {"fid": "f174", "field": "f174"},
}

# 最新交易日数据缓存 TTL（秒）：10 分钟内直接返回缓存，超过则重新请求东财
_CACHE_TTL = 600

# 每日 17:00 固化任务
_AUTO_UPDATE_TIME = (17, 0)


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
    url = (_API_URL + "?pn=1&pz=" + str(_PZ) + "&po=" + po + "&np=1&fltt=2&invt=2"
           "&fid=" + cfg["fid"] + "&fs=" + fs + "&fields=" + _FIELDS + "&ut=" + _EM_BKZJ_UT)
    data = jsonp_get(url)
    if not isinstance(data, dict) or "__error__" in data:
        return []
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


def _latest_trading_date() -> str:
    """返回最近一个A股交易日（YYYY-MM-DD）"""
    d = datetime.date.today()
    while not is_a_share_trading_day(d):
        d -= datetime.timedelta(days=1)
    return d.strftime('%Y-%m-%d')


def _updated_after_close(updated_at) -> bool:
    """判断 updated_at 是否在 A股收盘时间之后（缓存是否为收盘后落盘）。

    收盘后落盘的数据已定格，即使超过 10 分钟 TTL 也直接返回缓存，不再请求东财。
    """
    hours = get_market_hours('hs_main')
    if not hours:
        return False
    close_min = hours[2] * 60 + hours[3]
    dt = datetime.datetime.fromtimestamp(updated_at)
    return dt.hour * 60 + dt.minute >= close_min


def _fetch_rank(fs: str, sector_type: str, period: str, trade_date: str):
    """请求东财流入+流出排行，写入 sector_fund_rank，返回 (inflow, outflow)。
    空数据不落库，避免用空列表覆盖已有数据 / 固化空数据。"""
    inflow = _request_top(fs, period, po="1")
    outflow = _request_top(fs, period, po="0")
    if inflow or outflow:
        rank_set(trade_date, sector_type, period, inflow, outflow)
    return inflow, outflow


def _fetch_stocks(sector_code: str):
    """请求东财板块成分股（按涨跌幅排序），返回 (stocks, total)"""
    url = (_API_URL + "?pn=1&pz=100&po=1&np=1&fltt=2&invt=2"
           "&fid=f3&fs=b:" + sector_code + "&fields=" + _STOCK_FIELDS + "&ut=" + _EM_BKZJ_UT)
    data = jsonp_get(url)
    if not isinstance(data, dict) or "__error__" in data:
        return [], 0
    if not data.get("data") or not data["data"].get("diff"):
        return [], 0

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

    return stocks, total


def get_sector_fund(sector_type: str = "concept", period: str = "today", date: str = None) -> dict:
    """获取指定板块类型+时间段+交易日的资金流向排行（客户端触发，10 分钟缓存）。

    - date 为空时取最近一个交易日；
    - 非今天的日期：数据已固化，有缓存直接返回；无缓存仅最近交易日实时请求；
    - 今天的日期：10 分钟内直接返回缓存，超过 10 分钟重新请求东财。
    """
    if sector_type not in _SECTOR_TYPES:
        return {"success": False, "error": f"未知板块类型: {sector_type}"}
    if period not in _PERIOD_CONFIG:
        return {"success": False, "error": f"未知时间段: {period}"}

    trade_date = date or _latest_trading_date()
    today_str = datetime.date.today().strftime('%Y-%m-%d')

    cached = rank_get(trade_date, sector_type, period)
    if cached:
        inflow, outflow, updated_at = cached
        # 非今天的数据已固化，直接返回（不做 TTL 判断）
        if trade_date != today_str:
            return {"success": True, "date": trade_date, "inflow": inflow, "outflow": outflow}
        # 今天的数据：10 分钟内直接返回缓存
        if time.time() - updated_at < _CACHE_TTL:
            return {"success": True, "date": trade_date, "inflow": inflow, "outflow": outflow}
        # 超过 10 分钟：但若缓存是收盘后落盘的，数据已定格，直接返回缓存
        if _updated_after_close(updated_at):
            return {"success": True, "date": trade_date, "inflow": inflow, "outflow": outflow}
        # 盘中落盘的缓存过期 → 继续往下重新请求

    # 无缓存或今天缓存已过期：仅最近交易日才实时请求，更早的历史日期不请求
    if trade_date != _latest_trading_date():
        return {"success": True, "date": trade_date, "inflow": [], "outflow": [], "empty": True}

    # 最近交易日即今天，且今天尚未开盘 → 东财暂无当日数据，不请求直接返回空
    if trade_date == today_str and not is_market_opened('0'):
        return {"success": True, "date": trade_date, "inflow": [], "outflow": [], "empty": True}

    fs = _SECTOR_TYPES[sector_type]
    inflow, outflow = _fetch_rank(fs, sector_type, period, trade_date)
    return {"success": True, "date": trade_date, "inflow": inflow, "outflow": outflow}


def get_sector_stocks(sector_code: str, date: str = None) -> dict:
    """获取板块成分股列表。逻辑同 get_sector_fund（客户端触发，10 分钟缓存）。"""
    if not sector_code:
        return {"success": False, "error": "缺少板块编码"}

    trade_date = date or _latest_trading_date()
    today_str = datetime.date.today().strftime('%Y-%m-%d')

    cached = form_get(trade_date, sector_code)
    if cached:
        stocks, updated_at = cached
        if trade_date != today_str:
            return {"success": True, "stocks": stocks, "total": len(stocks)}
        if time.time() - updated_at < _CACHE_TTL:
            return {"success": True, "stocks": stocks, "total": len(stocks)}
        # 超过 10 分钟：但若缓存是收盘后落盘的，数据已定格，直接返回缓存
        if _updated_after_close(updated_at):
            return {"success": True, "stocks": stocks, "total": len(stocks)}
        # 盘中落盘的缓存过期 → 继续往下重新请求

    if trade_date != _latest_trading_date():
        return {"success": True, "stocks": [], "total": 0, "empty": True}

    if trade_date == today_str and not is_market_opened('0'):
        return {"success": True, "stocks": [], "total": 0, "empty": True}

    stocks, total = _fetch_stocks(sector_code)
    if stocks:
        form_set(trade_date, sector_code, stocks)
    return {"success": True, "stocks": stocks, "total": total}


# =========== 定时任务：每日 17:00 固化 ===========

_auto_next_update = None   # 下一次 17:00 任务时刻


def _next_update_time(base):
    """返回 base 当天 17:00；若已过则返回次日 17:00"""
    cand = base.replace(hour=_AUTO_UPDATE_TIME[0], minute=_AUTO_UPDATE_TIME[1],
                        second=0, microsecond=0)
    if cand <= base:
        cand = (base + datetime.timedelta(days=1)).replace(
            hour=_AUTO_UPDATE_TIME[0], minute=_AUTO_UPDATE_TIME[1],
            second=0, microsecond=0)
    return cand


def _run_daily_update():
    """每日 17:00 任务：清理过期数据，并统一全量落库当日排行榜 + 成分股。

    收盘后客户端请求不会再重新抓取（updated_at 收盘后直接返回缓存），
    所以 17:00 无条件全量抓取一次，把盘中快照覆盖为收盘最终数据。
    """
    cleanup_old_data()

    today = datetime.date.today()
    if not is_a_share_trading_day(today):
        print(f'[sector_fund] 17:00 任务跳过: {today} 非A股交易日')
        return
    trade_date = today.strftime('%Y-%m-%d')

    # 1. 全量抓取六种排行榜（覆盖盘中快照为收盘数据）
    for sector_type, fs in _SECTOR_TYPES.items():
        for period in _PERIOD_CONFIG:
            _fetch_rank(fs, sector_type, period, trade_date)

    # 2. 收集所有排行榜中的板块代码，全量抓成分股（覆盖）
    sector_codes = set()
    for sector_type in _SECTOR_TYPES:
        for period in _PERIOD_CONFIG:
            cached = rank_get(trade_date, sector_type, period)
            if not cached:
                continue
            for item in cached[0] + cached[1]:
                code = item.get('sector_code')
                if code:
                    sector_codes.add(code)

    done = 0
    for code in sector_codes:
        try:
            stocks, _ = _fetch_stocks(code)
            if stocks:
                form_set(trade_date, code, stocks)
            done += 1
        except Exception as e:
            print(f'[sector_fund] 成分股抓取失败 {code}: {e}')
    print(f'[sector_fund] 17:00 任务完成: {trade_date}，成分股落库 {done}/{len(sector_codes)} 个板块')


def check_sector_fund_update():
    """板块资金定时检测：由公共秒级调度器每秒调用一次，每日 17:00 触发固化。

    固化任务耗时较长（要补齐成分股），放到独立线程执行，避免阻塞调度器。
    """
    global _auto_next_update
    now_dt = datetime.datetime.now()
    if now_dt >= _auto_next_update:
        _auto_next_update = _next_update_time(now_dt)
        threading.Thread(target=_run_daily_update, daemon=True, name='sector-fund-daily').start()


def init_sector_fund_update():
    """初始化板块资金定时任务，返回检测函数供公共调度器注册（由 app.py 启动时调用）。"""
    global _auto_next_update
    now_dt = datetime.datetime.now()
    _auto_next_update = _next_update_time(now_dt)
    print(f'[sector_fund] 定时任务已初始化（17:00 固化下次: {_auto_next_update:%Y-%m-%d %H:%M}）')
    return check_sector_fund_update


# =========== ETF 持仓（与板块资金排行无关，保持不变） ===========

def _parse_fundf10_holdings(code: str, topline: int = 300, year: str = "") -> list:
    """从 fundf10 jjcc API 解析 ETF 持仓股票列表，返回 [{code, market, name, ratio, share_count, market_value, is_foreign}]"""
    params = {
        "type": "jjcc",
        "code": code,
        "topline": str(topline),
        "year": year,
        "month": "",
        "rt": "0.5",
    }
    text = get_text("https://fundf10.eastmoney.com/FundArchivesDatas.aspx",
                    params=params,
                    headers={"User-Agent": "Mozilla/5.0", "Referer": "https://fund.eastmoney.com/"},
                    timeout=15)

    # 响应格式: var apidata={ content:"...", ...}  — 从中提取 HTML content
    match = re.search(r'var apidata\s*=\s*\{.*?content:"(.*?)".*?\}', text, re.DOTALL)
    if not match:
        return []
    html_content = match.group(1)
    # content 里的转义引号还原
    html_content = html_content.replace('\\"', '"')

    # 取第一个季度section（即最新）
    sections = html_content.split("<div class='box'>")
    for section in sections[1:]:
        soup = BeautifulSoup(section, "html.parser")
        tbody = soup.find("tbody")
        if not tbody:
            continue

        rows = tbody.find_all("tr")
        if not rows:
            continue

        # 检测是否为境外股：td[1] 的 class 为 toc 表示境外股，tor 表示国内股
        first_row_tds = rows[0].find_all("td")
        is_qdii = len(first_row_tds) > 1 and "toc" in (first_row_tds[1].get("class") or [])

        stocks = []
        for tr in rows:
            tds = tr.find_all("td")
            if len(tds) < 9:
                continue
            # tds[0]=序号, tds[1]=股票代码, tds[2]=名称, tds[3]=最新价, tds[4]=涨跌幅,
            # tds[5]=相关资讯, tds[6]=占净值比例, tds[7]=持股数, tds[8]=持仓市值
            code_link = tds[1].find("a")
            stock_code = code_link.get_text(strip=True) if code_link else tds[1].get_text(strip=True)
            name_link = tds[2].find("a")
            stock_name = name_link.get_text(strip=True) if name_link else tds[2].get_text(strip=True)
            ratio = tds[6].get_text(strip=True)
            share_count = tds[7].get_text(strip=True)
            market_value = tds[8].get_text(strip=True)

            if is_qdii:
                # QDII: 区分港股(116)和美股(106)，数字代码为港股，字母代码为美股
                is_us = bool(re.match(r'^[A-Z]', stock_code, re.IGNORECASE))
                market = "106" if is_us else "116"
                stocks.append({
                    "code": stock_code,
                    "market": market,
                    "name": stock_name,
                    "ratio": ratio,
                    "share_count": share_count,
                    "market_value": market_value,
                    "is_foreign": True,
                })
            else:
                # 国内股：跳过非6位数字代码（如 A19121）
                if not re.match(r'^\d{6}$', stock_code):
                    continue
                # 上海(6xxxxx/688xxx) → market 1; 深圳/创业板/北交所 → market 0
                market = "1" if stock_code.startswith("6") else "0"
                stocks.append({
                    "code": stock_code,
                    "market": market,
                    "name": stock_name,
                    "ratio": ratio,
                    "share_count": share_count,
                    "market_value": market_value,
                    "is_foreign": False,
                })
        return stocks

    return []


def get_etf_stocks(code: str, market: str) -> dict:
    """获取ETF成分股列表（前端按占比排序）
    步骤：1) 从 fundf10 解析持仓股票代码  2) 用 ulist.np/get 获取实时行情
    """
    if not code or not market:
        return {"success": False, "error": "缺少参数"}

    # 从 fundf10 解析持仓，优先取当年（最新季度），当年无数据才退到去年
    cur_year = str(datetime.datetime.now().year)
    prev_year = str(datetime.datetime.now().year - 1)
    holdings = _parse_fundf10_holdings(code, topline=300, year=cur_year)
    if not holdings:
        holdings = _parse_fundf10_holdings(code, topline=300, year=prev_year)
    if not holdings:
        # 再试不指定年份（让 API 自行选择）
        holdings = _parse_fundf10_holdings(code, topline=300, year="")
    if not holdings:
        return {"success": True, "stocks": [], "total": 0}

    total = len(holdings)

    # 分两批请求行情：A股+港股走 ulist.np/get，美股走新浪 gb_ API
    quote_data = {}
    em_holdings = [h for h in holdings if is_a_share(h["market"]) or is_hk(h["market"])]
    us_holdings = [h for h in holdings if is_us(h["market"])]

    # 1) A股 + 港股 → 腾讯 qt.gtimg.cn（统一走 get_realtime_quotes_gtimg，字段 price/pct/name）
    if em_holdings:
        secids = ",".join(f"{h['market']}.{h['code']}" for h in em_holdings)
        try:
            quotes = get_realtime_quotes_gtimg(secids)
            for key, q in quotes.items():
                quote_data[key] = q
        except Exception:
            pass

    # 2) 美股 → 新浪 gb_ API（ulist.np/get 不支持美股，统一走 get_sina_hq）
    if us_holdings:
        us_codes = [f"gb_{h['code'].lower()}" for h in us_holdings]
        sina_hq = get_sina_hq(us_codes)
        for sina_code, payload in sina_hq.items():
            parts = payload.split(",")
            if len(parts) < 5:
                continue
            # gb_ 格式: name(0), price(1), change_pct%(2), datetime(3), change_val(4)
            us_code = sina_code.split("gb_")[-1].upper()
            quote_data[f"106.{us_code}"] = {
                "price": parts[1],
                "pct": parts[2],
                "code": us_code,
                "market": "106",
                "name": parts[0],
            }

    # 合并持仓 + 行情（统一字段 price/pct/name）
    stocks = []
    for h in holdings:
        key = f"{h['market']}.{h['code']}"
        q = quote_data.get(key)

        change_pct = _safe_float(q.get("pct", 0)) if q else None
        price = _safe_float(q.get("price", 0)) if q else None
        name = (q.get("name") or h["name"]) if q else h["name"]

        etf = is_etf(h["code"], h["market"])

        stocks.append({
            "name": name,
            "code": h["code"],
            "market": h["market"],
            "change_pct": f"{'+' if (change_pct or 0) >= 0 else ''}{(change_pct if change_pct is not None else 0):.2f}%" if change_pct is not None else "-",
            "price": fmt(price, etf) if price is not None else "-",
            "ratio": h["ratio"],
            "share_count": h["share_count"],
            "market_value": h["market_value"],
            "is_foreign": h.get("is_foreign", False),
        })

    # 排序由前端完成
    return {"success": True, "stocks": stocks, "total": total}
