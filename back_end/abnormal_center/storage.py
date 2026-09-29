"""异动中心 — SQLite 持久化存储（异动预测 + 异动监控 按交易日归档）"""
import datetime
import json
import os
import sqlite3
import time

from common.utils import is_a_share_trading_day

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'abnormal_center.db')

# 只保留最近 N 个交易日的数据（与前端日期栏的 30 个交易日对齐）
_KEEP_TRADING_DAYS = 30


def _db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute('''CREATE TABLE IF NOT EXISTS abnormal_prediction (
        trade_date  TEXT PRIMARY KEY,
        data        TEXT NOT NULL,
        updated_at  REAL NOT NULL
    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS abnormal_monitor (
        trade_date  TEXT PRIMARY KEY,
        data        TEXT NOT NULL,
        stats       TEXT NOT NULL,
        updated_at  REAL NOT NULL
    )''')
    conn.commit()
    return conn


def prediction_get(trade_date):
    """读取异动预测列表，返回 (data, updated_at) 或 None"""
    conn = _db()
    row = conn.execute(
        'SELECT data, updated_at FROM abnormal_prediction WHERE trade_date = ?',
        (trade_date,)).fetchone()
    conn.close()
    if row:
        return (json.loads(row[0]), row[1])
    return None


def prediction_set(trade_date, data):
    """写入异动预测列表"""
    conn = _db()
    conn.execute(
        'INSERT OR REPLACE INTO abnormal_prediction (trade_date, data, updated_at) '
        'VALUES (?, ?, ?)',
        (trade_date, json.dumps(data, ensure_ascii=False), time.time()))
    conn.commit()
    conn.close()


def monitor_get(trade_date):
    """读取异动监控列表，返回 (data, stats, updated_at) 或 None"""
    conn = _db()
    row = conn.execute(
        'SELECT data, stats, updated_at FROM abnormal_monitor WHERE trade_date = ?',
        (trade_date,)).fetchone()
    conn.close()
    if row:
        return (json.loads(row[0]), json.loads(row[1]), row[2])
    return None


def monitor_set(trade_date, data, stats):
    """写入异动监控列表"""
    conn = _db()
    conn.execute(
        'INSERT OR REPLACE INTO abnormal_monitor (trade_date, data, stats, updated_at) '
        'VALUES (?, ?, ?, ?)',
        (trade_date, json.dumps(data, ensure_ascii=False),
         json.dumps(stats, ensure_ascii=False), time.time()))
    conn.commit()
    conn.close()


def cleanup_old_data():
    """删除保留交易日数之前的数据（prediction + monitor）。

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
    r1 = conn.execute('DELETE FROM abnormal_prediction WHERE trade_date < ?', (cutoff,)).rowcount
    r2 = conn.execute('DELETE FROM abnormal_monitor WHERE trade_date < ?', (cutoff,)).rowcount
    conn.commit()
    conn.close()
    print(f'[abnormal_center] 清理过期数据: trade_date < {cutoff}，prediction 删除 {r1} 条，monitor 删除 {r2} 条')
