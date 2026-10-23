"""热股榜 — SQLite 持久化存储（榜单数据按自然日 + 榜单类型 + 周期落库）"""
import datetime
import json
import os
import sqlite3
import time

from common.utils import data_dir

DB_PATH = os.path.join(data_dir(), 'hot_stock.db')

# 只保留最近 N 个自然日的数据（与前端日期栏的 30 个自然日对齐）
_KEEP_DAYS = 30


def _db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute('''CREATE TABLE IF NOT EXISTS hot_stock_rank (
        date       TEXT NOT NULL,
        list_type  TEXT NOT NULL,
        period     TEXT NOT NULL,
        data       TEXT NOT NULL,
        updated_at REAL NOT NULL,
        PRIMARY KEY (date, list_type, period)
    )''')
    conn.commit()
    return conn


def rank_get(date, list_type, period):
    """读取榜单数据，返回 (stocks, updated_at) 或 None"""
    conn = _db()
    row = conn.execute(
        'SELECT data, updated_at FROM hot_stock_rank '
        'WHERE date = ? AND list_type = ? AND period = ?',
        (date, list_type, period)).fetchone()
    conn.close()
    if row:
        return (json.loads(row[0]), row[1])
    return None


def rank_set(date, list_type, period, stocks):
    """写入榜单数据（含落库时间）"""
    conn = _db()
    conn.execute(
        'INSERT OR REPLACE INTO hot_stock_rank (date, list_type, period, data, updated_at) '
        'VALUES (?, ?, ?, ?, ?)',
        (date, list_type, period, json.dumps(stocks, ensure_ascii=False), time.time()))
    conn.commit()
    conn.close()


def cleanup_old_data():
    """删除 _KEEP_DAYS 个自然日之前的数据"""
    cutoff = (datetime.date.today() - datetime.timedelta(days=_KEEP_DAYS)).strftime('%Y-%m-%d')
    conn = _db()
    r = conn.execute('DELETE FROM hot_stock_rank WHERE date < ?', (cutoff,)).rowcount
    conn.commit()
    conn.close()
    print(f'[hot_stock] 清理过期数据: date < {cutoff}，删除 {r} 条')
