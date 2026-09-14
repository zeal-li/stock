"""自动复盘数据持久化 — 独立 SQLite 存储
    data/self_review.db

每交易日由调度器收盘后自动跑一次大盘复盘并把结果存盘，便于历史回看与跨日对比。
自选复盘不在自动调度内（由用户主动触发即点即算）；stock_review 表预留给手动落盘场景。
单一数据源：复盘 JSON 整段入库，不做多源兜底。

两张表：
- market_review  大盘复盘（按交易日为主键，每日一条，自动生成）
- stock_review   自选复盘（按 交易日 + 用户 为主键，每日每用户一条，手动触发）
"""
import datetime
import json
import os
import sqlite3

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'self_review.db')


def _db():
    """打开/创建 DB 连接，建表幂等（沿用 sector_fund / money_flow 的 _db 风格）"""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS market_review (
            trade_date    TEXT PRIMARY KEY,        -- 复盘交易日 'YYYY-MM-DD'
            update_time   TEXT NOT NULL,          -- 复盘生成时间 'YYYY-MM-DD HH:MM:SS'
            market_status TEXT,                    -- 盘中/已收盘/休市
            data          TEXT NOT NULL           -- run_review()['data'] 的 JSON 串
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS stock_review (
            trade_date   TEXT NOT NULL,           -- 复盘交易日 'YYYY-MM-DD'
            user_id      TEXT NOT NULL,           -- 用户 ID（自选复盘按用户区分）
            update_time  TEXT NOT NULL,           -- 复盘生成时间 'YYYY-MM-DD HH:MM:SS'
            data         TEXT NOT NULL,           -- run_stock_review()['data'] 的 JSON 串
            PRIMARY KEY (trade_date, user_id)
        )
    ''')
    conn.execute(
        'CREATE INDEX IF NOT EXISTS idx_stock_review_user '
        'ON stock_review(user_id, trade_date DESC)'
    )
    conn.commit()
    return conn


def _now():
    return datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')


# ==================== market_review 大盘复盘 ====================

def save_market_review(trade_date, data, market_status=None, update_time=None):
    """落盘一次大盘复盘。trade_date 为 'YYYY-MM-DD' 交易日；data 为 run_review()['data']。
    同一交易日再次写入则覆盖（INSERT OR REPLACE）。"""
    conn = _db()
    conn.execute(
        'INSERT OR REPLACE INTO market_review (trade_date, update_time, market_status, data) '
        'VALUES (?,?,?,?)',
        (trade_date, update_time or _now(), market_status, json.dumps(data, ensure_ascii=False))
    )
    conn.commit()
    conn.close()


def get_market_review(trade_date):
    """取某交易日的大盘复盘，返回 {trade_date, update_time, market_status, data} 或 None"""
    conn = _db()
    row = conn.execute(
        'SELECT trade_date, update_time, market_status, data FROM market_review WHERE trade_date=?',
        (trade_date,)).fetchone()
    conn.close()
    if not row:
        return None
    return {
        'trade_date': row[0],
        'update_time': row[1],
        'market_status': row[2],
        'data': json.loads(row[3]),
    }


def list_market_reviews(limit=30):
    """最近 N 个有大盘复盘记录的交易日（按交易日降序）"""
    conn = _db()
    rows = conn.execute(
        'SELECT trade_date, update_time, market_status FROM market_review '
        'ORDER BY trade_date DESC LIMIT ?',
        (limit,)).fetchall()
    conn.close()
    return [{'trade_date': r[0], 'update_time': r[1], 'market_status': r[2]} for r in rows]


# ==================== stock_review 自选复盘 ====================

def save_stock_review(trade_date, user_id, data, update_time=None):
    """落盘一次自选复盘。trade_date 为 'YYYY-MM-DD' 交易日；data 为 run_stock_review()['data']。
    同一交易日同一用户再次写入则覆盖。"""
    conn = _db()
    conn.execute(
        'INSERT OR REPLACE INTO stock_review (trade_date, user_id, update_time, data) '
        'VALUES (?,?,?,?)',
        (trade_date, user_id, update_time or _now(), json.dumps(data, ensure_ascii=False))
    )
    conn.commit()
    conn.close()


def get_stock_review(trade_date, user_id):
    """取某用户某交易日的自选复盘，返回 {trade_date, user_id, update_time, data} 或 None"""
    conn = _db()
    row = conn.execute(
        'SELECT trade_date, user_id, update_time, data FROM stock_review '
        'WHERE trade_date=? AND user_id=?',
        (trade_date, user_id)).fetchone()
    conn.close()
    if not row:
        return None
    return {
        'trade_date': row[0],
        'user_id': row[1],
        'update_time': row[2],
        'data': json.loads(row[3]),
    }


def list_stock_reviews(user_id, limit=30):
    """某用户最近 N 个有自选复盘记录的交易日（按交易日降序）"""
    conn = _db()
    rows = conn.execute(
        'SELECT trade_date, update_time FROM stock_review WHERE user_id=? '
        'ORDER BY trade_date DESC LIMIT ?',
        (user_id, limit)).fetchall()
    conn.close()
    return [{'trade_date': r[0], 'update_time': r[1]} for r in rows]


# ==================== 跨天清理（保留最近 N 个交易日） ====================

def cleanup_old_reviews(keep_days=14):
    """保留最近 keep_days 个交易日的复盘数据，删除更早的。
    cutoff = market_review + stock_review 两表 trade_date 并集降序第 keep_days 个
    （即保留的最旧交易日），删除 trade_date < cutoff 的所有行。
    两表总交易日数不足 keep_days 个时直接返回 0（无需清理）。返回被删除的行数。"""
    conn = _db()
    rows = conn.execute(
        'SELECT trade_date FROM ('
        '  SELECT trade_date FROM market_review '
        '  UNION '
        '  SELECT trade_date FROM stock_review'
        ') ORDER BY trade_date DESC LIMIT ?',
        (keep_days,)).fetchall()
    if len(rows) < keep_days:
        conn.close()
        return 0
    cutoff = rows[-1][0]
    c1 = conn.execute('DELETE FROM market_review WHERE trade_date < ?', (cutoff,)).rowcount
    c2 = conn.execute('DELETE FROM stock_review WHERE trade_date < ?', (cutoff,)).rowcount
    conn.commit()
    conn.close()
    return c1 + c2
