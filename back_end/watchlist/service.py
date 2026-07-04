"""自选股 / 场内ETF / 持仓股 SQLite 持久化存储"""
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
    conn.execute('CREATE TABLE IF NOT EXISTS watchlist (code TEXT, market TEXT, created_at TEXT, added_price TEXT, sort_order INTEGER DEFAULT 0, PRIMARY KEY (code, market))')
    conn.execute('CREATE TABLE IF NOT EXISTS etf (code TEXT, market TEXT, created_at TEXT, added_price TEXT, sort_order INTEGER DEFAULT 0, PRIMARY KEY (code, market))')
    conn.execute('CREATE TABLE IF NOT EXISTS holdings (code TEXT, market TEXT, created_at TEXT, added_price TEXT, sort_order INTEGER DEFAULT 0, PRIMARY KEY (code, market))')
    # 迁移旧表：添加 sort_order 列（若不存在）
    for tbl in ('watchlist', 'etf', 'holdings'):
        cols = [r[1] for r in conn.execute('PRAGMA table_info(' + tbl + ')').fetchall()]
        if 'sort_order' not in cols:
            conn.execute('ALTER TABLE ' + tbl + ' ADD COLUMN sort_order INTEGER DEFAULT 0')
    conn.commit()
    return conn


# ==================== 自选股 ====================

def get_all():
    """获取所有自选股 [(code, market, created_at, added_price), ...] 按 sort_order 排序"""
    conn = _ensure_db()
    rows = conn.execute('SELECT code, market, created_at, added_price FROM watchlist ORDER BY sort_order ASC, created_at DESC').fetchall()
    conn.close()
    return rows


def add(code, market, added_price=''):
    """添加自选股，已存在则忽略"""
    from datetime import datetime
    conn = _ensure_db()
    # 新增股票排在末尾：取当前最大 sort_order + 1
    max_sort = conn.execute('SELECT COALESCE(MAX(sort_order), -1) FROM watchlist').fetchone()[0]
    conn.execute('INSERT OR IGNORE INTO watchlist (code, market, created_at, added_price, sort_order) VALUES (?, ?, ?, ?, ?)',
                 (code, market, datetime.now().isoformat(), str(added_price), max_sort + 1))
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


def reorder(items):
    """批量更新自选股排序，items = [(code, market, sort_order), ...]"""
    conn = _ensure_db()
    for code, market, sort_order in items:
        conn.execute('UPDATE watchlist SET sort_order = ? WHERE code = ? AND market = ?', (sort_order, code, market))
    conn.commit()
    conn.close()


# ==================== 场内ETF ====================

def etf_get_all():
    """获取所有场内ETF [(code, market, created_at, added_price), ...] 按 sort_order 排序"""
    conn = _ensure_db()
    rows = conn.execute('SELECT code, market, created_at, added_price FROM etf ORDER BY sort_order ASC, created_at DESC').fetchall()
    conn.close()
    return rows


def etf_add(code, market, added_price=''):
    """添加场内ETF，已存在则忽略"""
    from datetime import datetime
    conn = _ensure_db()
    max_sort = conn.execute('SELECT COALESCE(MAX(sort_order), -1) FROM etf').fetchone()[0]
    conn.execute('INSERT OR IGNORE INTO etf (code, market, created_at, added_price, sort_order) VALUES (?, ?, ?, ?, ?)',
                 (code, market, datetime.now().isoformat(), str(added_price), max_sort + 1))
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


def etf_reorder(items):
    """批量更新场内ETF排序，items = [(code, market, sort_order), ...]"""
    conn = _ensure_db()
    for code, market, sort_order in items:
        conn.execute('UPDATE etf SET sort_order = ? WHERE code = ? AND market = ?', (sort_order, code, market))
    conn.commit()
    conn.close()


# ==================== 持仓股 ====================

def holdings_get_all():
    """获取所有持仓股 [(code, market, created_at, added_price), ...] 按 sort_order 排序"""
    conn = _ensure_db()
    rows = conn.execute('SELECT code, market, created_at, added_price FROM holdings ORDER BY sort_order ASC, created_at DESC').fetchall()
    conn.close()
    return rows


def holdings_add(code, market, added_price=''):
    """添加持仓股，已存在则忽略"""
    from datetime import datetime
    conn = _ensure_db()
    max_sort = conn.execute('SELECT COALESCE(MAX(sort_order), -1) FROM holdings').fetchone()[0]
    conn.execute('INSERT OR IGNORE INTO holdings (code, market, created_at, added_price, sort_order) VALUES (?, ?, ?, ?, ?)',
                 (code, market, datetime.now().isoformat(), str(added_price), max_sort + 1))
    conn.commit()
    conn.close()


def holdings_remove(code, market):
    """删除持仓股"""
    conn = _ensure_db()
    conn.execute('DELETE FROM holdings WHERE code = ? AND market = ?', (code, market))
    conn.commit()
    conn.close()


def holdings_update_price(code, market, added_price):
    """更新持仓股加选价格"""
    conn = _ensure_db()
    conn.execute('UPDATE holdings SET added_price = ? WHERE code = ? AND market = ?', (str(added_price), code, market))
    conn.commit()
    conn.close()


def holdings_reorder(items):
    """批量更新持仓股排序，items = [(code, market, sort_order), ...]"""
    conn = _ensure_db()
    for code, market, sort_order in items:
        conn.execute('UPDATE holdings SET sort_order = ? WHERE code = ? AND market = ?', (sort_order, code, market))
    conn.commit()
    conn.close()
