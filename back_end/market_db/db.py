"""全市场股票数据存储 — 双文件
    data/stock_list.db      股票列表 + 同步日志
    data/stock_detail_list.db   K线 + 股票元信息
"""
import os
import sqlite3

_LIST_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'stock_list.db')
_DETAIL_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'stock_detail_list.db')


# ==================== 通用 ====================

def _connect(path, create_sqls):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    for sql in create_sqls if isinstance(create_sqls, list) else [create_sqls]:
        conn.execute(sql)
    conn.commit()
    return conn


# ==================== stock_list.db ====================

def _list_conn():
    return _connect(_LIST_PATH, [
        '''CREATE TABLE IF NOT EXISTS stocks (
            code TEXT NOT NULL, market TEXT NOT NULL, name TEXT,
            PRIMARY KEY (code, market))''',
        '''CREATE TABLE IF NOT EXISTS sync_log (
            market TEXT PRIMARY KEY,
            last_sync_date TEXT)''',
    ])


def list_stock_count():
    conn = _list_conn()
    n = conn.execute('SELECT COUNT(*) FROM stocks').fetchone()[0]
    conn.close()
    return n

def list_stocks_by_market():
    """{market: {code: name}}"""
    conn = _list_conn()
    rows = conn.execute('SELECT code, market, name FROM stocks ORDER BY code').fetchall()
    conn.close()
    result = {}
    for r in rows:
        result.setdefault(r['market'], {})[r['code']] = r['name']
    return result

def list_markets():
    """返回已存在的市场列表"""
    conn = _list_conn()
    rows = conn.execute('SELECT DISTINCT market FROM stocks').fetchall()
    conn.close()
    return [r['market'] for r in rows]

def list_stocks_all():
    """[(code, market, name), ...]"""
    conn = _list_conn()
    rows = conn.execute('SELECT code, market, name FROM stocks ORDER BY code').fetchall()
    conn.close()
    return [(r['code'], r['market'], r['name']) for r in rows]

def list_replace_market(market, rows):
    """替换指定市场的股票列表：rows=[(code,name), ...]"""
    conn = _list_conn()
    conn.execute('DELETE FROM stocks WHERE market=?', (market,))
    if rows:
        conn.executemany('INSERT INTO stocks (code, market, name) VALUES (?, ?, ?)',
                         [(c, market, n) for c, n in rows])
    conn.commit()
    conn.close()

def list_sync_date_get(market):
    """获取某市场上次同步日期"""
    conn = _list_conn()
    r = conn.execute('SELECT last_sync_date FROM sync_log WHERE market=?', (market,)).fetchone()
    conn.close()
    return r['last_sync_date'] if r else None

def list_sync_date_set(market, date_str):
    """设置某市场的同步日期"""
    conn = _list_conn()
    conn.execute('INSERT OR REPLACE INTO sync_log (market, last_sync_date) VALUES (?, ?)',
                 (market, date_str))
    conn.commit()
    conn.close()




# ==================== stock_detail_list.db ====================

def _detail_conn():
    conn = _connect(_DETAIL_PATH, [
        '''CREATE TABLE IF NOT EXISTS klines (
            code TEXT NOT NULL, market TEXT NOT NULL,
            period TEXT NOT NULL, date TEXT NOT NULL,
            open REAL, high REAL, low REAL, close REAL, volume REAL, amount REAL,
            PRIMARY KEY (code, market, period, date))''',
        '''CREATE TABLE IF NOT EXISTS stock_info (
            code TEXT NOT NULL, market TEXT NOT NULL,
            name TEXT, latest_kline_date TEXT,
            PRIMARY KEY (code, market))''',
        '''CREATE INDEX IF NOT EXISTS idx_klines_market ON klines(market, code, period, date)''',
    ])
    # WAL 模式：并发读写不互斥，崩溃恢复更可靠
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA synchronous=FULL')
    return conn


def detail_stock_count():
    conn = _detail_conn()
    n = conn.execute('SELECT COUNT(DISTINCT code||market) FROM stock_info').fetchone()[0]
    conn.close()
    return n

def detail_info_get(code, market):
    """获取单只股票元信息 {name, latest_kline_date}"""
    conn = _detail_conn()
    r = conn.execute('SELECT name, latest_kline_date FROM stock_info WHERE code=? AND market=?',
                     (code, market)).fetchone()
    conn.close()
    return dict(r) if r else None

def detail_info_upsert(code, market, name, kline_date):
    """插入或更新股票元信息"""
    conn = _detail_conn()
    conn.execute('INSERT OR REPLACE INTO stock_info (code, market, name, latest_kline_date) VALUES (?,?,?,?)',
                 (code, market, name, kline_date))
    conn.commit()
    conn.close()

def detail_info_all():
    """所有股票元信息 [(code, market, name, latest_kline_date), ...]"""
    conn = _detail_conn()
    rows = conn.execute('SELECT code, market, name, latest_kline_date FROM stock_info').fetchall()
    conn.close()
    return [(r['code'], r['market'], r['name'], r['latest_kline_date']) for r in rows]

def detail_info_date_map():
    """批量获取所有股票的 latest_kline_date，返回 {(code, market): date_str}，避免逐只查 DB"""
    conn = _detail_conn()
    rows = conn.execute('SELECT code, market, latest_kline_date FROM stock_info').fetchall()
    conn.close()
    return {(r['code'], r['market']): (r['latest_kline_date'] or '') for r in rows}

def detail_remove_stock(code, market):
    """删除某只股票的 K 线和元信息"""
    conn = _detail_conn()
    conn.execute('DELETE FROM klines WHERE code=? AND market=?', (code, market))
    conn.execute('DELETE FROM stock_info WHERE code=? AND market=?', (code, market))
    conn.commit()
    conn.close()


def detail_clear_market(market):
    """清除指定市场的所有 K 线和元信息"""
    conn = _detail_conn()
    conn.execute('DELETE FROM klines WHERE market=?', (market,))
    conn.execute('DELETE FROM stock_info WHERE market=?', (market,))
    conn.commit()
    conn.close()

def detail_klines_insert(rows):
    """rows: [(code, market, period, date, open, high, low, close, volume, amount), ...]"""
    if not rows:
        return
    conn = _detail_conn()
    conn.executemany(
        'INSERT OR IGNORE INTO klines (code,market,period,date,open,high,low,close,volume,amount) '
        'VALUES (?,?,?,?,?,?,?,?,?,?)', rows)
    conn.commit()
    conn.close()


def detail_sync_atomic(code, market, name, kline_rows, latest_date):
    """原子写入：K 线数据 + stock_info 在同一个事务中，保证中途重启不会丢进度"""
    conn = _detail_conn()
    try:
        conn.execute('BEGIN IMMEDIATE')
        for r in kline_rows:
            conn.execute(
                'INSERT OR IGNORE INTO klines (code,market,period,date,open,high,low,close,volume,amount) '
                'VALUES (?,?,?,?,?,?,?,?,?,?)', r)
        conn.execute(
            'INSERT OR REPLACE INTO stock_info (code, market, name, latest_kline_date) VALUES (?,?,?,?)',
            (code, market, name or code, latest_date))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def detail_klines_get(code, market, period, limit=300):
    conn = _detail_conn()
    rows = conn.execute(
        'SELECT date, open, high, low, close, volume, amount FROM klines '
        'WHERE code=? AND market=? AND period=? ORDER BY date DESC LIMIT ?',
        (code, market, period, limit)).fetchall()
    conn.close()
    return [dict(r) for r in reversed(rows)]

def detail_klines_batch(codes, market, period='daily', limit=120):
    """批量取多只股票 K 线：{code: [{date, open, ...}]}"""
    if not codes:
        return {}
    conn = _detail_conn()
    placeholders = ','.join('?' * len(codes))
    rows = conn.execute(
        f'SELECT code, date, open, high, low, close, volume, amount FROM klines '
        f'WHERE market=? AND period=? AND code IN ({placeholders}) ORDER BY code, date ASC',
        [market, period] + list(codes)).fetchall()
    conn.close()
    result = {}
    for r in rows:
        k = {'date': r['date'], 'open': r['open'], 'high': r['high'],
             'low': r['low'], 'close': r['close'], 'volume': r['volume'], 'amount': r['amount']}
        result.setdefault(r['code'], []).append(k)
    for code in result:
        if len(result[code]) > limit:
            result[code] = result[code][-limit:]
    return result
