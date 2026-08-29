"""用户认证：注册 / 登录 / 用户信息 SQLite 持久化"""
import os
import re
import sys as _sys
import hashlib
import sqlite3
import time

from common.utils import USER_TYPE_NORMAL, USER_TYPE_ROOT

if getattr(_sys, 'frozen', False):
    _DATA_DIR = os.path.join(os.path.dirname(_sys.executable), 'data')
else:
    _DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')

DB_PATH = os.path.join(_DATA_DIR, 'login.db')
CONFIG_DB_PATH = os.path.join(_DATA_DIR, 'config.db')


def _ensure_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        'CREATE TABLE IF NOT EXISTS users ('
        'id INTEGER PRIMARY KEY AUTOINCREMENT, '
        'username TEXT NOT NULL UNIQUE, '
        'password_hash TEXT NOT NULL, '
        'salt TEXT NOT NULL, '
        'create_time INTEGER NOT NULL, '
        'user_type INTEGER NOT NULL DEFAULT 0, '
        'session_version INTEGER NOT NULL DEFAULT 0, '
        'last_login_time INTEGER'
        ')'
    )
    # 已有库升级：补充 session_version 列（密码修改后 +1，使旧登录态失效）
    cols = [row[1] for row in conn.execute('PRAGMA table_info(users)')]
    if 'session_version' not in cols:
        conn.execute('ALTER TABLE users ADD COLUMN session_version INTEGER NOT NULL DEFAULT 0')
    conn.commit()
    # 建表时顺带创建默认 admin 用户（不存在才创建）
    exists = conn.execute("SELECT id FROM users WHERE username = 'admin'").fetchone()
    if not exists:
        salt = os.urandom(16).hex()
        password_hash = _hash_password('123456', salt)
        conn.execute(
            'INSERT INTO users (username, password_hash, salt, create_time, user_type) VALUES (?, ?, ?, ?, ?)',
            ('admin', password_hash, salt, int(time.time()), USER_TYPE_ROOT)
        )
        conn.commit()
    return conn


def _hash_password(password, salt):
    """对密码加盐哈希（sha256）"""
    return hashlib.sha256((salt + password).encode('utf-8')).hexdigest()


def init_secret_key():
    """服务器启动时调用：确保 config.db 及 app_config 表就绪，并准备 secret_key。

    secret_key 用于 Flask session 签名：
    - 已存在则直接读取（保证重启后登录态不失效）
    - 不存在则随机生成并持久化（避免硬编码泄露在源码里）
    返回准备好的 secret_key。
    """
    os.makedirs(os.path.dirname(CONFIG_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(CONFIG_DB_PATH)
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


def reset_secret_key():
    """重置 secret_key：随机生成新值并持久化，返回新密钥。"""
    os.makedirs(os.path.dirname(CONFIG_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(CONFIG_DB_PATH)
    conn.execute(
        'CREATE TABLE IF NOT EXISTS app_config ('
        'key TEXT PRIMARY KEY, '
        'value TEXT NOT NULL'
        ')'
    )
    secret_key = os.urandom(32).hex()
    conn.execute(
        "INSERT INTO app_config (key, value) VALUES ('secret_key', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (secret_key,)
    )
    conn.commit()
    conn.close()
    return secret_key


def get_app_config():
    """读取 config.db 中 app_config 表的所有配置项。返回 dict，键为配置 key，值为 value。"""
    os.makedirs(os.path.dirname(CONFIG_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(CONFIG_DB_PATH)
    conn.execute(
        'CREATE TABLE IF NOT EXISTS app_config ('
        'key TEXT PRIMARY KEY, '
        'value TEXT NOT NULL'
        ')'
    )
    rows = conn.execute('SELECT key, value FROM app_config').fetchall()
    conn.close()
    return {row[0]: row[1] for row in rows}


def validate_username(username):
    """校验用户名合法性。返回错误提示字符串；合法时返回空字符串 ''。"""
    username = (username or '').strip()
    if not username:
        return '用户名不能为空'
    if len(username) < 3:
        return '用户名至少 3 个字符'
    if len(username) > 32:
        return '用户名过长'
    if not re.fullmatch(r'[A-Za-z0-9_]+', username):
        return '用户名只能包含英文字母、数字和下划线'
    return ''


def validate_password(password):
    """校验密码合法性。返回错误提示字符串；合法时返回空字符串 ''。"""
    password = password or ''
    if not password:
        return '密码不能为空'
    if len(password) < 6:
        return '密码至少 6 位'
    if len(password) > 64:
        return '密码不能超过 64 位'
    return ''


def register(username, password):
    """注册用户。返回 (success: bool, message: str)"""
    username = (username or '').strip()
    password = password or ''
    error = validate_username(username)
    if error:
        return False, error
    error = validate_password(password)
    if error:
        return False, error

    conn = _ensure_db()
    exists = conn.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone()
    if exists:
        conn.close()
        return False, '用户名已存在'

    salt = os.urandom(16).hex()
    password_hash = _hash_password(password, salt)
    conn.execute(
        'INSERT INTO users (username, password_hash, salt, create_time, user_type) VALUES (?, ?, ?, ?, ?)',
        (username, password_hash, salt, int(time.time()), USER_TYPE_NORMAL)
    )
    conn.commit()
    conn.close()
    return True, '注册成功'


def login(username, password):
    """登录校验。返回 (success: bool, message: str, user_type: int, session_version: int)"""
    username = (username or '').strip()
    password = password or ''
    error = validate_username(username)
    if error:
        return False, error, USER_TYPE_NORMAL, 0
    error = validate_password(password)
    if error:
        return False, error, USER_TYPE_NORMAL, 0

    conn = _ensure_db()
    row = conn.execute(
        'SELECT password_hash, salt, user_type, session_version FROM users WHERE username = ?', (username,)
    ).fetchone()
    if not row:
        conn.close()
        return False, '用户名或密码错误', USER_TYPE_NORMAL, 0
    password_hash, salt, user_type, session_version = row
    if _hash_password(password, salt) != password_hash:
        conn.close()
        return False, '用户名或密码错误', USER_TYPE_NORMAL, 0
    conn.execute(
        'UPDATE users SET last_login_time = ? WHERE username = ?',
        (int(time.time()), username)
    )
    conn.commit()
    conn.close()
    return True, '登录成功', user_type, session_version


def get_user(username):
    """查询用户信息。返回 dict 或 None"""
    username = (username or '').strip()
    if not username:
        return None
    conn = _ensure_db()
    row = conn.execute(
        'SELECT id, username, user_type, create_time, last_login_time FROM users WHERE username = ?', (username,)
    ).fetchone()
    conn.close()
    if not row:
        return None
    return {'id': row[0], 'username': row[1], 'user_type': row[2], 'create_time': row[3], 'last_login_time': row[4]}


def get_all_users():
    """查询所有用户。返回用户列表（不含密码等敏感信息）"""
    conn = _ensure_db()
    rows = conn.execute(
        'SELECT id, username, user_type, create_time, last_login_time FROM users ORDER BY id ASC'
    ).fetchall()
    conn.close()
    return [
        {'id': row[0], 'username': row[1], 'user_type': row[2], 'create_time': row[3], 'last_login_time': row[4]}
        for row in rows
    ]


def get_user_by_id(user_id):
    """根据用户 id 查询用户信息。返回 dict 或 None"""
    conn = _ensure_db()
    row = conn.execute(
        'SELECT id, username, user_type, create_time, last_login_time FROM users WHERE id = ?', (user_id,)
    ).fetchone()
    conn.close()
    if not row:
        return None
    return {'id': row[0], 'username': row[1], 'user_type': row[2], 'create_time': row[3], 'last_login_time': row[4]}


def reset_password(user_id, new_password):
    """管理员重置指定用户密码。返回 (success: bool, message: str)"""
    new_password = new_password or ''
    error = validate_password(new_password)
    if error:
        return False, error
    conn = _ensure_db()
    row = conn.execute('SELECT salt FROM users WHERE id = ?', (user_id,)).fetchone()
    if not row:
        conn.close()
        return False, '用户不存在'
    salt = row[0]
    new_password_hash = _hash_password(new_password, salt)
    conn.execute(
        'UPDATE users SET password_hash = ?, session_version = session_version + 1 WHERE id = ?',
        (new_password_hash, user_id)
    )
    conn.commit()
    conn.close()
    return True, '密码修改成功'


def update_user_type(user_id, new_user_type):
    """修改指定用户的用户类型。返回 (success: bool, message: str)"""
    conn = _ensure_db()
    row = conn.execute('SELECT id, user_type FROM users WHERE id = ?', (user_id,)).fetchone()
    if not row:
        conn.close()
        return False, '用户不存在'
    if row[1] != new_user_type:
        conn.execute(
            'UPDATE users SET user_type = ?, session_version = session_version + 1 WHERE id = ?',
            (new_user_type, user_id)
        )
        conn.commit()
    conn.close()
    return True, '权限修改成功'


def delete_user(user_id):
    """删除指定用户。返回 (success: bool, message: str)"""
    conn = _ensure_db()
    row = conn.execute('SELECT id FROM users WHERE id = ?', (user_id,)).fetchone()
    if not row:
        conn.close()
        return False, '用户不存在'
    conn.execute('DELETE FROM users WHERE id = ?', (user_id,))
    conn.commit()
    conn.close()
    return True, '删除成功'


def get_user_id(username):
    """根据用户名查询用户 id。返回 int 或 None"""
    username = (username or '').strip()
    if not username:
        return None
    conn = _ensure_db()
    row = conn.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone()
    conn.close()
    if not row:
        return None
    return row[0]


def change_password(username, old_password, new_password):
    """修改密码。返回 (success: bool, message: str)"""
    username = (username or '').strip()
    old_password = old_password or ''
    new_password = new_password or ''
    error = validate_password(old_password)
    if error:
        return False, error
    error = validate_password(new_password)
    if error:
        return False, error

    conn = _ensure_db()
    row = conn.execute(
        'SELECT password_hash, salt FROM users WHERE username = ?', (username,)
    ).fetchone()
    if not row:
        conn.close()
        return False, '用户不存在'
    password_hash, salt = row
    if _hash_password(old_password, salt) != password_hash:
        conn.close()
        return False, '原密码错误'
    new_password_hash = _hash_password(new_password, salt)
    conn.execute(
        'UPDATE users SET password_hash = ?, session_version = session_version + 1 WHERE username = ?',
        (new_password_hash, username)
    )
    conn.commit()
    conn.close()
    return True, '密码修改成功'


def get_session_version(username):
    """查询用户当前会话版本号。返回 int；用户不存在返回 None"""
    username = (username or '').strip()
    if not username:
        return None
    conn = _ensure_db()
    row = conn.execute('SELECT session_version FROM users WHERE username = ?', (username,)).fetchone()
    conn.close()
    if not row:
        return None
    return row[0]
