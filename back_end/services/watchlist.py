"""自选股 SQLite 持久化存储"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'watchlist.db')


def _ensure_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute('CREATE TABLE IF NOT EXISTS watchlist (code TEXT, market TEXT, created_at TEXT, added_price TEXT, PRIMARY KEY (code, market))')
    # 旧表兼容：添加 added_price 列
    try:
        conn.execute('ALTER TABLE watchlist ADD COLUMN added_price TEXT DEFAULT ""')
    except sqlite3.OperationalError:
        pass  # 列已存在
    conn.commit()
    return conn


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
