"""全球外汇汇率行情（新浪财经 hq.sinajs.cn）"""

import requests
from common import BROWSER_HEADERS

_SINA_HEADERS = {
    **BROWSER_HEADERS,
    'Referer': 'https://finance.sina.com.cn',
}

FOREX_LIST = [
    # 离岸/在岸人民币（6个，与中国市场关联密切）
    {"code": "fx_susdcnh",  "name": "美元/离岸人民币"},
    {"code": "fx_seurcnh",  "name": "欧元/离岸人民币"},
    {"code": "fx_sgbpcnh",  "name": "英镑/离岸人民币"},
    {"code": "fx_sjpycnh",  "name": "日元/离岸人民币"},
    {"code": "fx_scnhhkd",  "name": "离岸人民币/港币"},
    {"code": "fx_susdcny",  "name": "美元/在岸人民币"},
    {"code": None,           "name": "",            "source": "gap"},
    {"code": None,           "name": "",            "source": "gap"},
    {"code": None,           "name": "",            "source": "gap"},
    {"code": None,           "name": "",            "source": "gap"},
]


def _make_forex_url(code: str) -> str:
    """生成新浪外汇行情页链接"""
    symbol = code[4:].upper()  # fx_susdcnh → USDCNH
    return f"https://finance.sina.com.cn/money/forex/hq/{symbol}.shtml"


def _parse_forex(item: str, cfg: dict) -> dict:
    """解析新浪外汇数据
    字段: 0时间, 1最新价, 2买价, 3昨收, 4成交量, 5今开, 6最高, 7最低,
          8最新价(重复), 9名称, 10涨跌幅%, 11涨跌额, 12振幅, 13-, 14 52周最高, 15 52周最低, 16-, 17日期
    """
    parts = item.split(",")
    if len(parts) < 12:
        return None

    price = float(parts[1])
    change_pct = float(parts[10])  # 如 0.37 表示 0.37%
    change_value = float(parts[11])

    # 动态精度：按价格量级调整
    if price >= 100:
        price_fmt = f"{price:.2f}"
    elif price >= 1:
        price_fmt = f"{price:.4f}"
    else:
        price_fmt = f"{price:.6f}"

    return {
        "name": cfg["name"],
        "price": price_fmt,
        "change": f"{change_value:+.6f}" if abs(change_value) < 0.01 else f"{change_value:+.4f}",
        "change_pct": f"{'+' if change_pct >= 0 else ''}{change_pct:.2f}%",
        "url": _make_forex_url(cfg["code"]),
    }


def get_forex_rates() -> dict:
    """批量获取外汇汇率行情（单次请求）"""
    real_items = [c for c in FOREX_LIST if c.get("source") != "gap"]
    codes = ",".join(c["code"] for c in real_items)
    url = "https://hq.sinajs.cn/list=" + codes
    r = requests.get(url, headers=_SINA_HEADERS, timeout=10)
    r.encoding = "gb2312"

    raw_lines = r.text.strip().split("\n")
    if len(raw_lines) != len(real_items):
        return {"success": False, "data": [], "error": f"响应行数不匹配: {len(raw_lines)} vs {len(real_items)}"}

    result = {"success": True, "data": []}
    real_idx = 0

    for cfg in FOREX_LIST:
        if cfg.get("source") == "gap":
            result["data"].append({"name": "", "price": "", "change": "", "change_pct": "", "url": "", "gap": True})
            continue
        data_str = raw_lines[real_idx].split('"')[1]
        real_idx += 1
        if not data_str.strip():
            return {"success": False, "data": [], "error": f"{cfg['name']} 无数据"}

        parsed = _parse_forex(data_str, cfg)
        if parsed is None:
            return {"success": False, "data": [], "error": f"{cfg['name']} 解析失败"}
        result["data"].append(parsed)

    return result
