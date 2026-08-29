"""自选股 / 场内ETF / 持仓股 SQLite 持久化存储（按用户隔离）"""
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
    conn.execute('CREATE TABLE IF NOT EXISTS watchlist (user_id INTEGER, code TEXT, market TEXT, created_at TEXT, added_price TEXT, sort_order INTEGER DEFAULT 0, PRIMARY KEY (user_id, code, market))')
    conn.execute('CREATE TABLE IF NOT EXISTS etf (user_id INTEGER, code TEXT, market TEXT, created_at TEXT, added_price TEXT, sort_order INTEGER DEFAULT 0, PRIMARY KEY (user_id, code, market))')
    conn.execute('CREATE TABLE IF NOT EXISTS holdings (user_id INTEGER, code TEXT, market TEXT, created_at TEXT, hold_price TEXT DEFAULT \'\', hold_qty TEXT DEFAULT \'\', sort_order INTEGER DEFAULT 0, PRIMARY KEY (user_id, code, market))')
    conn.commit()
    return conn


# ==================== 自选股 ====================

def get_all(user_id):
    """获取指定用户所有自选股 [(code, market, created_at, added_price), ...] 按 sort_order 排序"""
    conn = _ensure_db()
    rows = conn.execute('SELECT code, market, created_at, added_price FROM watchlist WHERE user_id = ? ORDER BY sort_order ASC, created_at DESC', (user_id,)).fetchall()
    conn.close()
    return rows


def add(user_id, code, market, added_price=''):
    """添加自选股，已存在则忽略"""
    from datetime import datetime
    conn = _ensure_db()
    # 新增股票排在末尾：取当前用户最大 sort_order + 1
    max_sort = conn.execute('SELECT COALESCE(MAX(sort_order), -1) FROM watchlist WHERE user_id = ?', (user_id,)).fetchone()[0]
    conn.execute('INSERT OR IGNORE INTO watchlist (user_id, code, market, created_at, added_price, sort_order) VALUES (?, ?, ?, ?, ?, ?)',
                 (user_id, code, market, datetime.now().isoformat(), str(added_price), max_sort + 1))
    conn.commit()
    conn.close()


def remove(user_id, code, market):
    """删除自选股"""
    conn = _ensure_db()
    conn.execute('DELETE FROM watchlist WHERE user_id = ? AND code = ? AND market = ?', (user_id, code, market))
    conn.commit()
    conn.close()


def update_price(user_id, code, market, added_price):
    """更新自选股加选价格"""
    conn = _ensure_db()
    conn.execute('UPDATE watchlist SET added_price = ? WHERE user_id = ? AND code = ? AND market = ?', (str(added_price), user_id, code, market))
    conn.commit()
    conn.close()


def reorder(user_id, items):
    """批量更新自选股排序，items = [(code, market, sort_order), ...]"""
    conn = _ensure_db()
    for code, market, sort_order in items:
        conn.execute('UPDATE watchlist SET sort_order = ? WHERE user_id = ? AND code = ? AND market = ?', (sort_order, user_id, code, market))
    conn.commit()
    conn.close()


# ==================== 场内ETF ====================

def etf_get_all(user_id):
    """获取指定用户所有场内ETF [(code, market, created_at, added_price), ...] 按 sort_order 排序"""
    conn = _ensure_db()
    rows = conn.execute('SELECT code, market, created_at, added_price FROM etf WHERE user_id = ? ORDER BY sort_order ASC, created_at DESC', (user_id,)).fetchall()
    conn.close()
    return rows


def etf_add(user_id, code, market, added_price=''):
    """添加场内ETF，已存在则忽略"""
    from datetime import datetime
    conn = _ensure_db()
    max_sort = conn.execute('SELECT COALESCE(MAX(sort_order), -1) FROM etf WHERE user_id = ?', (user_id,)).fetchone()[0]
    conn.execute('INSERT OR IGNORE INTO etf (user_id, code, market, created_at, added_price, sort_order) VALUES (?, ?, ?, ?, ?, ?)',
                 (user_id, code, market, datetime.now().isoformat(), str(added_price), max_sort + 1))
    conn.commit()
    conn.close()


def etf_remove(user_id, code, market):
    """删除场内ETF"""
    conn = _ensure_db()
    conn.execute('DELETE FROM etf WHERE user_id = ? AND code = ? AND market = ?', (user_id, code, market))
    conn.commit()
    conn.close()


def etf_reorder(user_id, items):
    """批量更新场内ETF排序，items = [(code, market, sort_order), ...]"""
    conn = _ensure_db()
    for code, market, sort_order in items:
        conn.execute('UPDATE etf SET sort_order = ? WHERE user_id = ? AND code = ? AND market = ?', (sort_order, user_id, code, market))
    conn.commit()
    conn.close()


# ==================== 持仓股 ====================

def holdings_get_all(user_id):
    """获取指定用户所有持仓股 [(code, market, created_at, hold_price, hold_qty), ...] 按 sort_order 排序"""
    conn = _ensure_db()
    rows = conn.execute('SELECT code, market, created_at, hold_price, hold_qty FROM holdings WHERE user_id = ? ORDER BY sort_order ASC, created_at DESC', (user_id,)).fetchall()
    conn.close()
    return rows


def holdings_add(user_id, code, market, hold_price='', hold_qty=''):
    """添加持仓股，已存在则忽略"""
    from datetime import datetime
    conn = _ensure_db()
    max_sort = conn.execute('SELECT COALESCE(MAX(sort_order), -1) FROM holdings WHERE user_id = ?', (user_id,)).fetchone()[0]
    conn.execute('INSERT OR IGNORE INTO holdings (user_id, code, market, created_at, hold_price, hold_qty, sort_order) VALUES (?, ?, ?, ?, ?, ?, ?)',
                 (user_id, code, market, datetime.now().isoformat(), str(hold_price), str(hold_qty), max_sort + 1))
    conn.commit()
    conn.close()


def holdings_remove(user_id, code, market):
    """删除持仓股"""
    conn = _ensure_db()
    conn.execute('DELETE FROM holdings WHERE user_id = ? AND code = ? AND market = ?', (user_id, code, market))
    conn.commit()
    conn.close()


def holdings_update(user_id, code, market, hold_price=None, hold_qty=None):
    """更新持仓股持仓价和/或持仓数"""
    conn = _ensure_db()
    if hold_price is not None:
        conn.execute('UPDATE holdings SET hold_price = ? WHERE user_id = ? AND code = ? AND market = ?', (str(hold_price), user_id, code, market))
    if hold_qty is not None:
        conn.execute('UPDATE holdings SET hold_qty = ? WHERE user_id = ? AND code = ? AND market = ?', (str(hold_qty), user_id, code, market))
    conn.commit()
    conn.close()


def holdings_reorder(user_id, items):
    """批量更新持仓股排序，items = [(code, market, sort_order), ...]"""
    conn = _ensure_db()
    for code, market, sort_order in items:
        conn.execute('UPDATE holdings SET sort_order = ? WHERE user_id = ? AND code = ? AND market = ?', (sort_order, user_id, code, market))
    conn.commit()
    conn.close()


def delete_user_data(user_id):
    """删除指定用户的全部自选股、场内ETF、持仓股数据"""
    conn = _ensure_db()
    conn.execute('DELETE FROM watchlist WHERE user_id = ?', (user_id,))
    conn.execute('DELETE FROM etf WHERE user_id = ?', (user_id,))
    conn.execute('DELETE FROM holdings WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()
