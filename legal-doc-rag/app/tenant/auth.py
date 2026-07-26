import os
import hashlib
import secrets
import sqlite3
from pathlib import Path
from typing import Optional, Tuple, Dict


def _db_path() -> str:
    """返回 users.db 的路径（相对于项目根目录）"""
    base = Path(__file__).resolve().parent.parent.parent
    db_dir = base / "tenant_data"
    db_dir.mkdir(parents=True, exist_ok=True)
    return str(db_dir / "users.db")


def _init_db():
    """初始化数据库表"""
    db = _db_path()
    conn = sqlite3.connect(db)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            tenant_id TEXT NOT NULL,
            role TEXT DEFAULT 'user',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tenants (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


def _hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100000)
    return salt + "$" + h.hex()


def _verify_password(password: str, stored: str) -> bool:
    salt, h = stored.split("$")
    v = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100000)
    return h == v.hex()


def register(username: str, password: str) -> Tuple[bool, str]:
    """注册新用户 + 创建租户。返回 (成功, 消息)"""
    _init_db()
    conn = sqlite3.connect(_db_path())
    try:
        # 检查是否存在
        cur = conn.execute("SELECT id FROM users WHERE username=?", (username,))
        if cur.fetchone():
            return False, "用户名已存在"

        # 生成租户 ID
        tenant_id = secrets.token_hex(4)  # 8字符
        conn.execute(
            "INSERT INTO tenants (id, name) VALUES (?, ?)",
            (tenant_id, f"{username}_tenant"),
        )
        # 创建用户
        conn.execute(
            "INSERT INTO users (username, password_hash, tenant_id, role) VALUES (?, ?, ?, ?)",
            (username, _hash_password(password), tenant_id, "admin"),
        )
        conn.commit()
        return True, f"注册成功，租户ID: {tenant_id}"
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        conn.close()


def login(username: str, password: str) -> Tuple[bool, Optional[Dict]]:
    """用户登录。返回 (成功, 用户信息或错误消息)"""
    _init_db()
    conn = sqlite3.connect(_db_path())
    try:
        cur = conn.execute(
            "SELECT id, username, password_hash, tenant_id, role FROM users WHERE username=?",
            (username,),
        )
        row = cur.fetchone()
        if not row:
            return False, {"error": "用户名或密码错误"}
        if not _verify_password(password, row[2]):
            return False, {"error": "用户名或密码错误"}
        return True, {
            "id": row[0],
            "username": row[1],
            "tenant_id": row[3],
            "role": row[4],
        }
    finally:
        conn.close()


def has_users() -> bool:
    """检查是否已有用户"""
    _init_db()
    conn = sqlite3.connect(_db_path())
    try:
        cur = conn.execute("SELECT COUNT(*) FROM users")
        return cur.fetchone()[0] > 0
    finally:
        conn.close()