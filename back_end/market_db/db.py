"""全市场股票数据存储 — 单文件
    data/stock_lib.db
"""
import os
import sqlite3

_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'stock_lib.db')


def _conn():
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA synchronous=FULL')
    return conn


def _init_tables(conn):
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS stock_market (
            market       TEXT PRIMARY KEY,
            sync_ts      TEXT,
            list_sync_ts TEXT
        );

        CREATE TABLE IF NOT EXISTS market_stock_list (
            code   TEXT NOT NULL,
            market TEXT NOT NULL,
            name   TEXT,
            PRIMARY KEY (code, market)
        );

        CREATE TABLE IF NOT EXISTS stock_klines (
            code     TEXT NOT NULL,
            market   TEXT NOT NULL,
            period   TEXT NOT NULL,
            date     TEXT NOT NULL,
            open     REAL,
            high     REAL,
            low      REAL,
            close    REAL,
            volume   REAL,
            amount   REAL,
            turnover REAL,
            PRIMARY KEY (code, market, period, date)
        );
        CREATE INDEX IF NOT EXISTS idx_klines_market ON stock_klines(market, code, period, date);

        CREATE TABLE IF NOT EXISTS stock_info (
            code       TEXT NOT NULL,
            market     TEXT NOT NULL,
            name       TEXT,
            daily_ts   TEXT,
            weekly_ts  TEXT,
            monthly_ts TEXT,
            PRIMARY KEY (code, market)
        );
    ''')


# ==================== stock_market ====================

def market_get(market):
    """获取市场行 {market, sync_ts, list_sync_ts}"""
    c = _conn()
    _init_tables(c)
    r = c.execute('SELECT * FROM stock_market WHERE market=?', (market,)).fetchone()
    c.close()
    return dict(r) if r else None


def market_all():
    """所有市场 key 列表"""
    c = _conn()
    _init_tables(c)
    rows = c.execute('SELECT market FROM stock_market').fetchall()
    c.close()
    return [r['market'] for r in rows]


def market_sync_ts_get(market):
    """获取某市场 K线上次同步完成时间"""
    r = market_get(market)
    return r['sync_ts'] if r and r['sync_ts'] else None


def market_sync_ts_set(market, ts_str):
    """设置某市场 K线同步时间"""
    c = _conn()
    _init_tables(c)
    c.execute('''INSERT INTO stock_market (market, sync_ts) VALUES (?,?)
                 ON CONFLICT(market) DO UPDATE SET sync_ts=excluded.sync_ts''', (market, ts_str))
    c.commit()
    c.close()


def market_list_ts_get(market):
    """获取某市场股票列表上次拉取时间"""
    r = market_get(market)
    return r['list_sync_ts'] if r and r['list_sync_ts'] else None


def market_list_ts_set(market, ts_str):
    """设置某市场股票列表拉取时间"""
    c = _conn()
    _init_tables(c)
    c.execute('''INSERT INTO stock_market (market, list_sync_ts) VALUES (?,?)
                 ON CONFLICT(market) DO UPDATE SET list_sync_ts=excluded.list_sync_ts''', (market, ts_str))
    c.commit()
    c.close()


def market_remove(market):
    """删除某市场"""
    c = _conn()
    _init_tables(c)
    c.execute('DELETE FROM stock_market WHERE market=?', (market,))
    c.commit()
    c.close()


# ==================== market_stock_list ====================

def stock_list_all():
    """[(code, market, name), ...]"""
    c = _conn()
    _init_tables(c)
    rows = c.execute('SELECT code, market, name FROM market_stock_list ORDER BY code').fetchall()
    c.close()
    return [(r['code'], r['market'], r['name']) for r in rows]


def stock_list_by_market():
    """{market: {code: name}}"""
    c = _conn()
    _init_tables(c)
    rows = c.execute('SELECT code, market, name FROM market_stock_list ORDER BY code').fetchall()
    c.close()
    result = {}
    for r in rows:
        result.setdefault(r['market'], {})[r['code']] = r['name']
    return result


def stock_list_replace_market(market, rows):
    """替换指定市场的股票列表：rows=[(code, name), ...]"""
    c = _conn()
    _init_tables(c)
    c.execute('DELETE FROM market_stock_list WHERE market=?', (market,))
    if rows:
        c.executemany('INSERT INTO market_stock_list (code, market, name) VALUES (?,?,?)',
                      [(code, market, name) for code, name in rows])
    c.commit()
    c.close()


def stock_list_count():
    """股票列表总数"""
    c = _conn()
    _init_tables(c)
    n = c.execute('SELECT COUNT(*) FROM market_stock_list').fetchone()[0]
    c.close()
    return n


# ==================== stock_klines ====================

def klines_get(code, market, period, limit=300):
    c = _conn()
    _init_tables(c)
    rows = c.execute(
        'SELECT date, open, high, low, close, volume, amount FROM stock_klines '
        'WHERE code=? AND market=? AND period=? ORDER BY date DESC LIMIT ?',
        (code, market, period, limit)).fetchall()
    c.close()
    return [dict(r) for r in reversed(rows)]


def klines_batch(codes, market, period='daily', limit=120):
    """批量取多只股票 K 线：{code: [{date, open, ...}]}"""
    if not codes:
        return {}
    c = _conn()
    _init_tables(c)
    placeholders = ','.join('?' * len(codes))
    rows = c.execute(
        f'SELECT code, date, open, high, low, close, volume, amount FROM stock_klines '
        f'WHERE market=? AND period=? AND code IN ({placeholders}) ORDER BY code, date ASC',
        [market, period] + list(codes)).fetchall()
    c.close()
    result = {}
    for r in rows:
        k = {'date': r['date'], 'open': r['open'], 'high': r['high'],
             'low': r['low'], 'close': r['close'], 'volume': r['volume'], 'amount': r['amount']}
        result.setdefault(r['code'], []).append(k)
    for code in result:
        if len(result[code]) > limit:
            result[code] = result[code][-limit:]
    return result


def klines_count_market(market):
    """某市场有K线的股票数"""
    c = _conn()
    _init_tables(c)
    n = c.execute('SELECT COUNT(DISTINCT code) FROM stock_klines WHERE market=?', (market,)).fetchone()[0]
    c.close()
    return n


def klines_years(code, market, period):
    """返回该股票该周期在库里已有的年份集合 {'2024','2025',...}"""
    c = _conn()
    _init_tables(c)
    rows = c.execute(
        'SELECT DISTINCT substr(date,1,4) AS y FROM stock_klines '
        'WHERE code=? AND market=? AND period=?', (code, market, period)).fetchall()
    c.close()
    return {r['y'] for r in rows}


def klines_get_by_years(code, market, period, years):
    """读取指定年份集合的K线，按日期升序返回 [{date, open, high, low, close, volume, amount}, ...]"""
    if not years:
        return []
    c = _conn()
    _init_tables(c)
    placeholders = ','.join('?' * len(years))
    rows = c.execute(
        f'SELECT date, open, high, low, close, volume, amount, turnover FROM stock_klines '
        f'WHERE code=? AND market=? AND period=? AND substr(date,1,4) IN ({placeholders}) '
        f'ORDER BY date ASC',
        [code, market, period] + list(years)).fetchall()
    c.close()
    return [dict(r) for r in rows]


# ==================== stock_info ====================

def stock_info_all():
    """所有股票元信息 [(code, market), ...]"""
    c = _conn()
    _init_tables(c)
    rows = c.execute('SELECT code, market FROM stock_info').fetchall()
    c.close()
    return [(r['code'], r['market']) for r in rows]


def stock_info_get(code, market):
    """获取单只股票元信息 {name, daily_ts, weekly_ts, monthly_ts} 或 None"""
    c = _conn()
    _init_tables(c)
    r = c.execute('SELECT name, daily_ts, weekly_ts, monthly_ts FROM stock_info WHERE code=? AND market=?',
                  (code, market)).fetchone()
    c.close()
    return dict(r) if r else None


def stock_info_kline_maps():
    """返回 (daily_map, weekly_map, monthly_map) 每个 {(code, market): ts_str}"""
    c = _conn()
    _init_tables(c)
    rows = c.execute('SELECT code, market, daily_ts, weekly_ts, monthly_ts FROM stock_info').fetchall()
    c.close()
    daily = {}
    weekly = {}
    monthly = {}
    for r in rows:
        k = (r['code'], r['market'])
        if r['daily_ts']:
            daily[k] = r['daily_ts']
        if r['weekly_ts']:
            weekly[k] = r['weekly_ts']
        if r['monthly_ts']:
            monthly[k] = r['monthly_ts']
    return daily, weekly, monthly


def stock_info_sync_atomic(code, market, name, kline_rows, period_dates):
    """原子写入：K线 + stock_info（per-period 时间戳）在同一事务
    period_dates: {'daily': ts, 'weekly': ts, 'monthly': ts} 只包含本次实际拉取的周期
    """
    c = _conn()
    _init_tables(c)
    try:
        c.execute('BEGIN IMMEDIATE')
        for r in kline_rows:
            c.execute(
                'INSERT OR IGNORE INTO stock_klines (code,market,period,date,open,high,low,close,volume,amount,turnover) '
                'VALUES (?,?,?,?,?,?,?,?,?,?,?)', r)

        # 读旧时间戳，只更新本次拉取的周期
        old = c.execute(
            'SELECT name, daily_ts, weekly_ts, monthly_ts FROM stock_info WHERE code=? AND market=?',
            (code, market)).fetchone()
        nd = period_dates.get('daily') or (old['daily_ts'] if old else None)
        nw = period_dates.get('weekly') or (old['weekly_ts'] if old else None)
        nm = period_dates.get('monthly') or (old['monthly_ts'] if old else None)
        new_name = name or (old['name'] if old else code)
        c.execute(
            'INSERT OR REPLACE INTO stock_info (code, market, name, daily_ts, weekly_ts, monthly_ts) '
            'VALUES (?,?,?,?,?,?)',
            (code, market, new_name, nd, nw, nm))
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()


def stock_info_remove(code, market):
    """删除某只股票的 K线和元信息"""
    c = _conn()
    _init_tables(c)
    c.execute('DELETE FROM stock_klines WHERE code=? AND market=?', (code, market))
    c.execute('DELETE FROM stock_info WHERE code=? AND market=?', (code, market))
    c.commit()
    c.close()


def stock_info_clear_market(market):
    """清除指定市场的所有 K线和元信息"""
    c = _conn()
    _init_tables(c)
    c.execute('DELETE FROM stock_klines WHERE market=?', (market,))
    c.execute('DELETE FROM stock_info WHERE market=?', (market,))
    c.commit()
    c.close()
