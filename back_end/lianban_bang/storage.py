"""连板榜 — SQLite 持久化存储（按交易日落库）"""
import datetime
import json
import os
import sqlite3
import time

from common.utils import data_dir

DB_PATH = os.path.join(data_dir(), 'lianban_bang.db')

# 只保留最近 N 个自然日的数据
_KEEP_DAYS = 30


def _db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute('''CREATE TABLE IF NOT EXISTS lianban_bang (
        trade_date TEXT PRIMARY KEY,
        data       TEXT NOT NULL,
        updated_at REAL NOT NULL
    )''')
    conn.commit()
    return conn


def rank_get(trade_date):
    """读取某交易日数据，返回 (list, updated_at) 或 None"""
    conn = _db()
    row = conn.execute(
        'SELECT data, updated_at FROM lianban_bang WHERE trade_date = ?',
        (trade_date,)).fetchone()
    conn.close()
    if row:
        return (json.loads(row[0]), row[1])
    return None


def rank_set(trade_date, rows):
    """写入某交易日数据（含落库时间）"""
    conn = _db()
    conn.execute(
        'INSERT OR REPLACE INTO lianban_bang (trade_date, data, updated_at) VALUES (?, ?, ?)',
        (trade_date, json.dumps(rows, ensure_ascii=False), time.time()))
    conn.commit()
    conn.close()


def cleanup_old_data():
    """删除 _KEEP_DAYS 个自然日之前的数据"""
    cutoff = (datetime.date.today() - datetime.timedelta(days=_KEEP_DAYS)).strftime('%Y-%m-%d')
    conn = _db()
    r = conn.execute('DELETE FROM lianban_bang WHERE trade_date < ?', (cutoff,)).rowcount
    conn.commit()
    conn.close()
    print(f'[lianban_bang] 清理过期数据: trade_date < {cutoff}，删除 {r} 条')
