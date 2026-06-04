"""自选股 SQLite 持久化存储"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'watchlist.db')


def _ensure_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute('CREATE TABLE IF NOT EXISTS watchlist (code TEXT, market TEXT, created_at TEXT, PRIMARY KEY (code, market))')
    conn.commit()
    return conn


def get_all():
    """获取所有自选股 [(code, market), ...]"""
    conn = _ensure_db()
    rows = conn.execute('SELECT code, market FROM watchlist ORDER BY created_at DESC').fetchall()
    conn.close()
    return rows


def add(code, market):
    """添加自选股，已存在则忽略"""
    from datetime import datetime
    conn = _ensure_db()
    conn.execute('INSERT OR IGNORE INTO watchlist (code, market, created_at) VALUES (?, ?, ?)',
                 (code, market, datetime.now().isoformat()))
    conn.commit()
    conn.close()


def remove(code, market):
    """删除自选股"""
    conn = _ensure_db()
    conn.execute('DELETE FROM watchlist WHERE code = ? AND market = ?', (code, market))
    conn.commit()
    conn.close()
