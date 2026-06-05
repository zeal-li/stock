"""全市场股票数据 SQLite 存储"""
import os
import sqlite3
import json

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'market.db')


def _conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('''CREATE TABLE IF NOT EXISTS stocks (
        code TEXT NOT NULL, market TEXT NOT NULL DEFAULT '0', name TEXT,
        PRIMARY KEY (code, market))''')
    conn.execute('''CREATE TABLE IF NOT EXISTS klines (
        code TEXT NOT NULL, market TEXT NOT NULL DEFAULT '0',
        period TEXT NOT NULL, date TEXT NOT NULL,
        open REAL, high REAL, low REAL, close REAL, volume REAL, amount REAL,
        PRIMARY KEY (code, market, period, date))''')
    conn.commit()
    return conn


# ---- 股票列表 ----

def stock_count():
    conn = _conn()
    n = conn.execute('SELECT COUNT(*) FROM stocks').fetchone()[0]
    conn.close()
    return n


def stocks_save(rows):
    """rows: [(code, market, name), ...]"""
    conn = _conn()
    conn.execute('DELETE FROM stocks')
    conn.executemany('INSERT OR REPLACE INTO stocks (code, market, name) VALUES (?, ?, ?)', rows)
    conn.commit()
    conn.close()


def stocks_all():
    conn = _conn()
    rows = conn.execute('SELECT code, market, name FROM stocks ORDER BY code').fetchall()
    conn.close()
    return [(r['code'], r['market'], r['name']) for r in rows]


# ---- K 线 ----

def kline_latest_date(code, market, period):
    conn = _conn()
    row = conn.execute(
        'SELECT MAX(date) as d FROM klines WHERE code=? AND market=? AND period=?',
        (code, market, period)).fetchone()
    conn.close()
    return row['d'] if row else None


def kline_count(code, market, period):
    conn = _conn()
    n = conn.execute(
        'SELECT COUNT(*) FROM klines WHERE code=? AND market=? AND period=?',
        (code, market, period)).fetchone()[0]
    conn.close()
    return n


def klines_insert(rows):
    """rows: [(code, market, period, date, open, high, low, close, volume, amount), ...]"""
    if not rows:
        return
    conn = _conn()
    conn.executemany(
        'INSERT OR IGNORE INTO klines (code,market,period,date,open,high,low,close,volume,amount) '
        'VALUES (?,?,?,?,?,?,?,?,?,?)', rows)
    conn.commit()
    conn.close()


def klines_get(code, market, period, limit=300):
    conn = _conn()
    rows = conn.execute(
        'SELECT date, open, high, low, close, volume, amount FROM klines '
        'WHERE code=? AND market=? AND period=? ORDER BY date DESC LIMIT ?',
        (code, market, period, limit)).fetchall()
    conn.close()
    return [dict(r) for r in reversed(rows)]
