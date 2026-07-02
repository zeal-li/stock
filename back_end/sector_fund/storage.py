"""板块资金 — 独立 SQLite 缓存存储"""
import json
import os
import sqlite3
import time

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'sector_fund.db')


def _db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute('CREATE TABLE IF NOT EXISTS sector_fund (key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at REAL NOT NULL)')
    conn.commit()
    return conn


def cache_get(key):
    """读取缓存，返回 (value, timestamp) 或 None"""
    conn = _db()
    row = conn.execute('SELECT value, updated_at FROM sector_fund WHERE key = ?', (key,)).fetchone()
    conn.close()
    if row:
        return (json.loads(row[0]), row[1])
    return None


def cache_set(key, value):
    """写入缓存，记录当前时间戳"""
    conn = _db()
    conn.execute('INSERT OR REPLACE INTO sector_fund (key, value, updated_at) VALUES (?, ?, ?)',
                 (key, json.dumps(value, ensure_ascii=False), time.time()))
    conn.commit()
    conn.close()


def is_fresh(key, ttl=10):
    """检查缓存是否在 ttl 秒内"""
    row = cache_get(key)
    if row:
        return time.time() - row[1] < ttl
    return False
