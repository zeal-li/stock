"""龙虎榜数据（同花顺）"""
import datetime
import json
import os
import sqlite3
import requests
from bs4 import BeautifulSoup
from common import REQUEST_PROXIES

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    'Referer': 'https://data.10jqka.com.cn/market/longhu/',
}

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'longhu_bang.db')


def _db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute('''CREATE TABLE IF NOT EXISTS longhu_bang (
        trade_date TEXT PRIMARY KEY,
        data TEXT NOT NULL,
        created_at TEXT DEFAULT (datetime('now'))
    )''')
    conn.commit()
    return conn

def cleanup_old_data():
    """删除 3 个月前的数据"""
    cutoff = (datetime.date.today() - datetime.timedelta(days=90)).strftime("%Y-%m-%d")
    conn = _db()
    cur = conn.execute('DELETE FROM longhu_bang WHERE trade_date < ?', (cutoff,))
    deleted = cur.rowcount
    conn.commit()
    conn.close()
    print(f"[longhu] 清理龙虎榜库: 删除 trade_date < {cutoff} 的记录，共 {deleted} 条")


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

    # stockcont: rid -> {seats, reason}
    seat_map, reason_map = _parse_stockcont(soup)

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

        # 上榜原因：从 stockcont 的 <p> 标签提取
        reason = reason_map.get(rid, '')

        result.append({
            "code": code,
            "name": name,
            "price": price,
            "change_pct": change_pct,
            "amount_raw": amount_raw,
            "net_amt": net_amt,
            "multi_day": multi_day_label,
            "buy_seats": buy_seats,
            "sell_seats": sell_seats,
            "reason": reason,
            "trade_date": trade_date,
        })

    if not result:
        return {"success": True, "data": {"trade_date": trade_date, "list": []}}

    return {"success": True, "data": {"trade_date": trade_date, "list": result}}


def _parse_stockcont(soup):
    """解析所有 stockcont div 的席位明细 + 上榜原因"""
    seat_map = {}
    reason_map = {}

    for sc in soup.select('.stockcont'):
        rid = sc.get('rid', '')
        if not rid:
            continue

        # 提取上榜原因：<p>股票名(代码)明细：原因</p>
        p_el = sc.find('p')
        if p_el:
            p_text = p_el.get_text(strip=True)
            # 格式: "国华退(000004)明细：退市整理证券"
            if '明细：' in p_text:
                reason_map[rid] = p_text.split('明细：', 1)[1].strip()
            elif '：' in p_text:
                reason_map[rid] = p_text.split('：', 1)[1].strip()

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

    return seat_map, reason_map


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


def get_longhu_bang(trade_date: str = None):
    """获取龙虎榜数据。先从 DB 缓存读取，没有则爬取后入库。返回当天的全部原始数据。"""
    if not trade_date:
        trade_date = datetime.date.today().strftime("%Y-%m-%d")

    # 1. 查 DB 缓存
    conn = _db()
    row = conn.execute('SELECT data FROM longhu_bang WHERE trade_date = ?', (trade_date,)).fetchone()
    if row:
        conn.close()
        return {"success": True, "data": json.loads(row[0])}

    # 2. DB 无数据，爬取
    raw = _fetch_longhu_bang(trade_date)
    if not raw.get("success"):
        conn.close()
        return raw

    data = raw["data"]

    # 3. 有数据则入库
    conn.execute('INSERT OR REPLACE INTO longhu_bang (trade_date, data) VALUES (?, ?)',
                 (trade_date, json.dumps(data, ensure_ascii=False)))
    conn.commit()
    conn.close()

    return {"success": True, "data": data}


# =========== 每日跨天清理（定时检测） ===========
# 每天跨天（00:00 之后）执行一次：删除 3 个月前的龙虎榜数据。
# 实现方式：维护一个"下一次执行时刻" _auto_next_cleanup，启动时初始化为明天 00:00
# （无论何时启动，当天都不触发）；调度器每秒检测，越过该时刻就执行一次清理，
# 并把下一次执行时刻推进到次日 00:00，如此每天一次。

_AUTO_CLEANUP_TIME = (0, 0)   # 触发时刻（时, 分）——跨天即每天零点
_auto_next_cleanup = None     # 下一次应执行清理的时刻（datetime）


def _next_cleanup_time(base):
    """返回 base 下一天的 00:00（每日跨天清理应执行的时刻）"""
    nxt = base + datetime.timedelta(days=1)
    return nxt.replace(
        hour=_AUTO_CLEANUP_TIME[0], minute=_AUTO_CLEANUP_TIME[1], second=0, microsecond=0)


def check_daily_cleanup():
    """龙虎榜库每日跨天清理检测：当前时间越过下次执行时刻后，执行一次清理。
    由 app.py 的公共秒级调度器每秒调用一次。"""
    global _auto_next_cleanup
    now = datetime.datetime.now()
    if now < _auto_next_cleanup:
        return
    # 以当前时间（而非 _auto_next_cleanup）为基准推次日 00:00：
    # 即使某次因故迟醒跨越了多个执行点，也只会补跑一次，不会连环补跑
    _auto_next_cleanup = _next_cleanup_time(now)
    cleanup_old_data()


def init_longhu_bang_update():
    """初始化龙虎榜库每日跨天清理的触发时刻，返回检测函数供公共调度器注册（由 app.py 启动时调用）。

    下一次执行时刻初始化为"明天 00:00"：无论何时启动，当天都不会触发，
    首次清理统一发生在次日凌晨 00:00 之后，此后每天一次。
    """
    global _auto_next_cleanup
    _auto_next_cleanup = _next_cleanup_time(datetime.datetime.now())
    print(f"[longhu] 龙虎榜每日跨天清理已初始化（下次执行: {_auto_next_cleanup:%Y-%m-%d %H:%M}）")
    return check_daily_cleanup
