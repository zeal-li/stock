"""龙虎榜数据（同花顺）"""
import datetime
import requests
from bs4 import BeautifulSoup
from common import REQUEST_PROXIES

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    'Referer': 'https://data.10jqka.com.cn/market/longhu/',
}

def _fetch_longhu_bang(trade_date: str = None):
    """从同花顺 lhbggxq 获取龙虎榜每日明细 + 席位分类"""
    if not trade_date:
        trade_date = datetime.date.today().strftime("%Y-%m-%d")

    url = f"https://data.10jqka.com.cn/ifmarket/lhbggxq/report/{trade_date}/"
    r = requests.get(url, params={'stock': 'all', 'tab': 'all'},
                     headers=HEADERS, timeout=15, proxies=REQUEST_PROXIES)
    soup = BeautifulSoup(r.text, 'html.parser')

    # --- 1. 解析 leftcol 股票汇总表 ---
    leftcol = soup.select_one('.leftcol')
    if not leftcol:
        return {"success": False, "error": "同花顺龙虎榜页面格式变化，未找到 leftcol"}

    # stockcont 席位明细：rid -> seat rows
    seat_map = _parse_stockcont(soup)

    # 解析 leftcol 表格行
    left_tbody = leftcol.select_one('.twrap tbody')
    if not left_tbody:
        left_tbody = leftcol.select_one('table.m-table tbody')

    result = []
    seen_rids = set()

    for tr in left_tbody.find_all('tr') if left_tbody else []:
        tds = tr.find_all('td')
        if len(tds) < 6:
            continue

        # td[0]: label (e.g., "3日", "7日") or empty
        label_td = tds[0]
        multi_day_label = ''
        label_el = label_td.find('label')
        if label_el:
            multi_day_label = label_el.get_text(strip=True)

        # td[1]: 股票代码
        code = tds[1].get_text(strip=True)

        # td[2]: 名称 + rid
        name_td = tds[2]
        name_link = name_td.find('a')
        name = name_link.get_text(strip=True) if name_link else ''
        rid = name_link.get('rid', '') if name_link else ''

        if not rid or rid in seen_rids:
            continue
        seen_rids.add(rid)

        # td[3]: 现价
        price_str = tds[3].get_text(strip=True)
        try:
            price = float(price_str)
        except ValueError:
            price = None

        # td[4]: 涨跌幅
        change_str = tds[4].get_text(strip=True).replace('%', '')
        try:
            change_pct = float(change_str)
        except ValueError:
            change_pct = None

        # td[5]: 成交金额 (带"万"/"亿"单位)
        amount_str = tds[5].get_text(strip=True)
        amount_raw = _parse_amount(amount_str)

        # td[6]: 净买入额
        net_str = tds[6].get_text(strip=True)
        net_amt = _parse_amount(net_str)

        # 席位明细
        seats = seat_map.get(rid, {})
        buy_seats = seats.get('buy', [])
        sell_seats = seats.get('sell', [])

        # 分类：机构 vs 游资
        has_jg = any('机构专用' in s['name'] for s in buy_seats) or \
                 any('机构专用' in s['name'] for s in sell_seats)
        has_yz_labels = any(s['label'] for s in buy_seats) or \
                        any(s['label'] for s in sell_seats)

        if has_jg and has_yz_labels:
            lhb_type = 'both'
        elif has_jg:
            lhb_type = 'org'
        elif has_yz_labels:
            lhb_type = 'capital'
        else:
            lhb_type = 'other'

        # 统计上榜原因
        reasons = []
        if multi_day_label:
            reasons.append(multi_day_label)
        # 从席位标签也提取原因
        all_labels = set()
        for s in buy_seats + sell_seats:
            if s['label']:
                all_labels.add(s['label'])
        if all_labels:
            reasons.extend(sorted(all_labels))

        result.append({
            "code": code,
            "name": name,
            "price": price,
            "change_pct": change_pct,
            "amount_raw": amount_raw,
            "net_amt": net_amt,
            "multi_day": multi_day_label,
            "lhb_type": lhb_type,
            "buy_seats": buy_seats,
            "sell_seats": sell_seats,
            "reason": '、'.join(reasons) if reasons else '',
            "buy_seat_count": len(buy_seats),
            "sell_seat_count": len(sell_seats),
            "trade_date": trade_date,
        })

    if not result:
        return {"success": True, "data": {"trade_date": trade_date, "list": []}}

    return {"success": True, "data": {"trade_date": trade_date, "list": result}}


def _parse_stockcont(soup):
    """解析所有 stockcont div 的席位明细"""
    seat_map = {}

    for sc in soup.select('.stockcont'):
        rid = sc.get('rid', '')
        if not rid:
            continue

        tables = sc.find_all('table', class_='m-table')
        buy_seats = []
        sell_seats = []

        for table in tables:
            thead_th = table.select_one('thead th')
            if not thead_th:
                continue
            header_text = thead_th.get_text(strip=True)
            is_buy = '买入' in header_text

            tbody = table.find('tbody')
            if not tbody:
                continue

            for tr in tbody.find_all('tr'):
                tds = tr.find_all('td')
                if len(tds) < 4:
                    continue

                # 席位名从 <a> 的 title 属性取全名，否则用文本
                a_el = tds[0].find('a')
                if a_el:
                    seat_name = a_el.get('title', '') or a_el.get_text(strip=True)
                else:
                    seat_name = tds[0].get_text(strip=True)
                # 席位标签（游资标签）从 <label> 取
                label_el = tds[0].find('label')
                seat_label = label_el.get_text(strip=True) if label_el else ''

                try:
                    buy_amt = (float(tds[1].get_text(strip=True)) * 10000) if tds[1].get_text(strip=True) else 0
                except ValueError:
                    buy_amt = 0
                try:
                    sell_amt = (float(tds[2].get_text(strip=True)) * 10000) if tds[2].get_text(strip=True) else 0
                except ValueError:
                    sell_amt = 0
                try:
                    net_val = (float(tds[3].get_text(strip=True)) * 10000) if tds[3].get_text(strip=True) else 0
                except ValueError:
                    net_val = 0

                seat_info = {
                    "name": seat_name,
                    "label": seat_label,
                    "buy_amt": buy_amt,
                    "sell_amt": sell_amt,
                    "net_amt": net_val,
                }

                if is_buy:
                    buy_seats.append(seat_info)
                else:
                    sell_seats.append(seat_info)

        seat_map[rid] = {"buy": buy_seats, "sell": sell_seats}

    return seat_map


def _parse_amount(s):
    """解析金额字符串: '94.49万' -> 944900, '-1.76亿' -> -176000000"""
    if not s or s == '--':
        return None
    s = s.strip()
    negative = s.startswith('-')
    if negative:
        s = s[1:]

    try:
        if s.endswith('万亿'):
            val = float(s[:-2]) * 1000000000000
        elif s.endswith('亿'):
            val = float(s[:-1]) * 100000000
        elif s.endswith('万'):
            val = float(s[:-1]) * 10000
        else:
            val = float(s)
        return -val if negative else val
    except ValueError:
        return None


def get_longhu_bang(trade_date: str = None, tab: str = 'all'):
    """获取龙虎榜数据，支持分类筛选"""
    raw = _fetch_longhu_bang(trade_date)

    if not raw.get("success"):
        return raw

    data = raw["data"]
    all_list = data.get("list", [])

    # 按 tab 筛选
    tab_map = {
        'all': lambda _: True,
        'org': lambda r: r['lhb_type'] in ('org', 'both'),
        'capital': lambda r: r['lhb_type'] in ('capital', 'both'),
        'both': lambda r: r['lhb_type'] == 'both',
    }

    filtered = [r for r in all_list if tab_map.get(tab, tab_map['all'])(r)]

    # 精简输出
    output = []
    for r in filtered:
        total_buy = sum(s['buy_amt'] for s in r['buy_seats'])
        total_sell = sum(s['sell_amt'] for s in r['sell_seats'])
        output.append({
            "code": r["code"],
            "name": r["name"],
            "price": r["price"],
            "change_pct": r["change_pct"],
            "net_amt": r["net_amt"],
            "amount_raw": r["amount_raw"],
            "total_buy": total_buy,
            "total_sell": total_sell,
            "lhb_type": r["lhb_type"],
            "multi_day": r["multi_day"],
            "reason": r["reason"],
            "buy_seat_count": r["buy_seat_count"],
            "sell_seat_count": r["sell_seat_count"],
            "trade_date": r["trade_date"],
            # 席位详情
            "buy_seats": r["buy_seats"],
            "sell_seats": r["sell_seats"],
        })

    return {"success": True, "data": {"trade_date": data["trade_date"], "list": output}}
