"""自选股 / 场内ETF SQLite 持久化存储"""
import sqlite3
import os
import sys as _sys

if getattr(_sys, 'frozen', False):
    DB_PATH = os.path.join(os.path.dirname(_sys.executable), 'data', 'watchlist.db')
else:
    DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'watchlist.db')


def _ensure_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute('CREATE TABLE IF NOT EXISTS watchlist (code TEXT, market TEXT, created_at TEXT, added_price TEXT, PRIMARY KEY (code, market))')
    conn.execute('CREATE TABLE IF NOT EXISTS etf (code TEXT, market TEXT, created_at TEXT, added_price TEXT, PRIMARY KEY (code, market))')
    conn.commit()
    return conn


# ==================== 自选股 ====================

def get_all():
    """获取所有自选股 [(code, market, created_at, added_price), ...]"""
    conn = _ensure_db()
    rows = conn.execute('SELECT code, market, created_at, added_price FROM watchlist ORDER BY created_at DESC').fetchall()
    conn.close()
    return rows


def add(code, market, added_price=''):
    """添加自选股，已存在则忽略"""
    from datetime import datetime
    conn = _ensure_db()
    conn.execute('INSERT OR IGNORE INTO watchlist (code, market, created_at, added_price) VALUES (?, ?, ?, ?)',
                 (code, market, datetime.now().isoformat(), str(added_price)))
    conn.commit()
    conn.close()


def remove(code, market):
    """删除自选股"""
    conn = _ensure_db()
    conn.execute('DELETE FROM watchlist WHERE code = ? AND market = ?', (code, market))
    conn.commit()
    conn.close()


def update_price(code, market, added_price):
    """更新自选股加选价格"""
    conn = _ensure_db()
    conn.execute('UPDATE watchlist SET added_price = ? WHERE code = ? AND market = ?', (str(added_price), code, market))
    conn.commit()
    conn.close()


# ==================== 场内ETF ====================

def etf_get_all():
    """获取所有场内ETF [(code, market, created_at, added_price), ...]"""
    conn = _ensure_db()
    rows = conn.execute('SELECT code, market, created_at, added_price FROM etf ORDER BY created_at DESC').fetchall()
    conn.close()
    return rows


def etf_add(code, market, added_price=''):
    """添加场内ETF，已存在则忽略"""
    from datetime import datetime
    conn = _ensure_db()
    conn.execute('INSERT OR IGNORE INTO etf (code, market, created_at, added_price) VALUES (?, ?, ?, ?)',
                 (code, market, datetime.now().isoformat(), str(added_price)))
    conn.commit()
    conn.close()


def etf_remove(code, market):
    """删除场内ETF"""
    conn = _ensure_db()
    conn.execute('DELETE FROM etf WHERE code = ? AND market = ?', (code, market))
    conn.commit()
    conn.close()


def etf_update_price(code, market, added_price):
    """更新场内ETF加选价格"""
    conn = _ensure_db()
    conn.execute('UPDATE etf SET added_price = ? WHERE code = ? AND market = ?', (str(added_price), code, market))
    conn.commit()
    conn.close()
