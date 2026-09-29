"""板块资金 — SQLite 持久化存储（排行榜 + 板块成分股）"""
import datetime
import json
import os
import sqlite3
import time

from common.utils import is_a_share_trading_day

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'sector_fund.db')

# 只保留最近 N 个交易日的数据（与前端日期栏的 30 个交易日对齐）
_KEEP_TRADING_DAYS = 30


def _db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute('''CREATE TABLE IF NOT EXISTS sector_fund_rank (
        trade_date  TEXT NOT NULL,
        sector_type TEXT NOT NULL,
        period      TEXT NOT NULL,
        inflow      TEXT NOT NULL,
        outflow     TEXT NOT NULL,
        updated_at  REAL NOT NULL,
        PRIMARY KEY (trade_date, sector_type, period)
    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS sector_fund_form (
        trade_date  TEXT NOT NULL,
        sector_code TEXT NOT NULL,
        data        TEXT NOT NULL,
        updated_at  REAL NOT NULL,
        PRIMARY KEY (trade_date, sector_code)
    )''')
    conn.commit()
    return conn


def rank_get(trade_date, sector_type, period):
    """读取排行榜，返回 (inflow, outflow, updated_at) 或 None"""
    conn = _db()
    row = conn.execute(
        'SELECT inflow, outflow, updated_at FROM sector_fund_rank '
        'WHERE trade_date = ? AND sector_type = ? AND period = ?',
        (trade_date, sector_type, period)).fetchone()
    conn.close()
    if row:
        return (json.loads(row[0]), json.loads(row[1]), row[2])
    return None


def rank_set(trade_date, sector_type, period, inflow, outflow):
    """写入排行榜"""
    conn = _db()
    conn.execute(
        'INSERT OR REPLACE INTO sector_fund_rank '
        '(trade_date, sector_type, period, inflow, outflow, updated_at) '
        'VALUES (?, ?, ?, ?, ?, ?)',
        (trade_date, sector_type, period,
         json.dumps(inflow, ensure_ascii=False),
         json.dumps(outflow, ensure_ascii=False), time.time()))
    conn.commit()
    conn.close()


def form_get(trade_date, sector_code):
    """读取板块成分股列表，返回 (list, updated_at) 或 None"""
    conn = _db()
    row = conn.execute(
        'SELECT data, updated_at FROM sector_fund_form WHERE trade_date = ? AND sector_code = ?',
        (trade_date, sector_code)).fetchone()
    conn.close()
    if row:
        return (json.loads(row[0]), row[1])
    return None


def form_set(trade_date, sector_code, data):
    """写入板块成分股列表"""
    conn = _db()
    conn.execute(
        'INSERT OR REPLACE INTO sector_fund_form (trade_date, sector_code, data, updated_at) '
        'VALUES (?, ?, ?, ?)',
        (trade_date, sector_code, json.dumps(data, ensure_ascii=False), time.time()))
    conn.commit()
    conn.close()


def cleanup_old_data():
    """删除保留交易日数之前的数据（rank + form）。

    保留最近 _KEEP_TRADING_DAYS 个交易日，删除更早的记录。
    """
    d = datetime.date.today()
    kept_dates = []
    while len(kept_dates) < _KEEP_TRADING_DAYS:
        if is_a_share_trading_day(d):
            kept_dates.append(d)
        d -= datetime.timedelta(days=1)
    cutoff = kept_dates[-1].strftime('%Y-%m-%d')

    conn = _db()
    r1 = conn.execute('DELETE FROM sector_fund_rank WHERE trade_date < ?', (cutoff,)).rowcount
    r2 = conn.execute('DELETE FROM sector_fund_form WHERE trade_date < ?', (cutoff,)).rowcount
    conn.commit()
    conn.close()
    print(f'[sector_fund] 清理过期数据: trade_date < {cutoff}，rank 删除 {r1} 条，form 删除 {r2} 条')
