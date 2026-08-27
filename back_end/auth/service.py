"""用户认证：注册 / 登录 / 用户信息 SQLite 持久化"""
import os
import sys as _sys
import hashlib
import sqlite3
import time

if getattr(_sys, 'frozen', False):
    DB_PATH = os.path.join(os.path.dirname(_sys.executable), 'data', 'user.db')
else:
    DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'user.db')


def _ensure_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        'CREATE TABLE IF NOT EXISTS users ('
        'id INTEGER PRIMARY KEY AUTOINCREMENT, '
        'username TEXT NOT NULL UNIQUE, '
        'password_hash TEXT NOT NULL, '
        'salt TEXT NOT NULL, '
        'create_time INTEGER NOT NULL'
        ')'
    )
    conn.commit()
    return conn


def _hash_password(password, salt):
    """对密码加盐哈希（sha256）"""
    return hashlib.sha256((salt + password).encode('utf-8')).hexdigest()


def _get_or_create_secret_key():
    """从 user.db 读取持久化的 secret_key，不存在则随机生成并写入。

    用于 Flask session 签名，保证服务重启后已登录用户不失效，
    同时避免密钥硬编码在源码里。
    """
    conn = _ensure_db()
    conn.execute(
        'CREATE TABLE IF NOT EXISTS app_config ('
        'key TEXT PRIMARY KEY, '
        'value TEXT NOT NULL'
        ')'
    )
    row = conn.execute("SELECT value FROM app_config WHERE key = 'secret_key'").fetchone()
    if row:
        conn.close()
        return row[0]
    secret_key = os.urandom(32).hex()
    conn.execute(
        "INSERT INTO app_config (key, value) VALUES ('secret_key', ?)",
        (secret_key,)
    )
    conn.commit()
    conn.close()
    return secret_key


def get_secret_key():
    """获取（必要时生成）Flask session 签名密钥"""
    return _get_or_create_secret_key()


def register(username, password):
    """注册用户。返回 (success: bool, message: str)"""
    username = (username or '').strip()
    password = password or ''
    if not username or not password:
        return False, '用户名和密码不能为空'
    if len(username) > 32:
        return False, '用户名过长'
    if len(password) < 6:
        return False, '密码至少 6 位'

    conn = _ensure_db()
    exists = conn.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone()
    if exists:
        conn.close()
        return False, '用户名已存在'

    salt = os.urandom(16).hex()
    password_hash = _hash_password(password, salt)
    conn.execute(
        'INSERT INTO users (username, password_hash, salt, create_time) VALUES (?, ?, ?, ?)',
        (username, password_hash, salt, int(time.time()))
    )
    conn.commit()
    conn.close()
    return True, '注册成功'


def login(username, password):
    """登录校验。返回 (success: bool, message: str)"""
    username = (username or '').strip()
    password = password or ''
    if not username or not password:
        return False, '用户名和密码不能为空'

    conn = _ensure_db()
    row = conn.execute(
        'SELECT password_hash, salt FROM users WHERE username = ?', (username,)
    ).fetchone()
    conn.close()
    if not row:
        return False, '用户名或密码错误'
    password_hash, salt = row
    if _hash_password(password, salt) != password_hash:
        return False, '用户名或密码错误'
    return True, '登录成功'
