import os
import hashlib
import secrets
import sqlite3
from pathlib import Path
from typing import Optional, Tuple, Dict, List

import app.core.config as cfg


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
    # 文档分类表
    conn.execute("""
        CREATE TABLE IF NOT EXISTS document_categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id TEXT NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(tenant_id, name)
        )
    """)
    # 文档表（用于存储文档元数据和分类）
    conn.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id TEXT NOT NULL,
            filename TEXT NOT NULL,
            category_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (category_id) REFERENCES document_categories(id),
            UNIQUE(tenant_id, filename)
        )
    """)
    # 对话历史表
    conn.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            title TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # 对话消息表
    conn.execute("""
        CREATE TABLE IF NOT EXISTS conversation_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
        )
    """)
        # 迁移: 将现有 admin 升级为 super_admin
    try:
        conn.execute("UPDATE users SET role = 'super_admin' WHERE role = 'admin'")
    except Exception:
        pass
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
        cur = conn.execute("SELECT COUNT(*) FROM users")
        user_count = cur.fetchone()[0]
        role = "super_admin" if user_count == 0 else "user"
        conn.execute(
            "INSERT INTO users (username, password_hash, tenant_id, role) VALUES (?, ?, ?, ?)",
            (username, _hash_password(password), tenant_id, role),
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


def list_users() -> List[Dict]:
    """列出所有用户（供管理后台使用）。返回字典列表。"""
    _init_db()
    conn = sqlite3.connect(_db_path())
    try:
        cur = conn.execute(
            "SELECT id, username, tenant_id, role, created_at FROM users ORDER BY id"
        )
        rows = cur.fetchall()
        return [
            {
                "user_id": r[0],
                "username": r[1],
                "tenant_id": r[2],
                "role": r[3],
                "created_at": r[4],
            }
            for r in rows
        ]
    finally:
        conn.close()


def delete_user(username: str) -> bool:
    """删除指定用户。返回是否实际删除了记录。"""
    _init_db()
    conn = sqlite3.connect(_db_path())
    try:
        cur = conn.execute("DELETE FROM users WHERE username=?", (username,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def set_user_role(username: str, role: str) -> Tuple[bool, str]:
    """修改用户角色（super_admin / user）。管理后台提权/降级用。"""
    if role not in ("super_admin", "user"):
        return False, "无效的角色"
    _init_db()
    conn = sqlite3.connect(_db_path())
    try:
        cur = conn.execute("SELECT id FROM users WHERE username=?", (username,))
        if not cur.fetchone():
            return False, "用户不存在"
        conn.execute(
            "UPDATE users SET role=? WHERE username=?", (role, username)
        )
        conn.commit()
        return True, f"已将 {username} 的角色设为 {role}"
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        conn.close()


def change_password(username: str, old_password: str, new_password: str) -> Tuple[bool, str]:
    """修改密码。需先校验原密码，返回 (成功, 消息)。"""
    _init_db()
    conn = sqlite3.connect(_db_path())
    try:
        cur = conn.execute(
            "SELECT id, password_hash FROM users WHERE username=?", (username,)
        )
        row = cur.fetchone()
        if not row:
            return False, "用户不存在"
        if not _verify_password(old_password, row[1]):
            return False, "原密码错误"
        if not new_password or len(new_password) < 6:
            return False, "新密码长度至少 6 位"
        conn.execute(
            "UPDATE users SET password_hash=? WHERE username=?",
            (_hash_password(new_password), username),
        )
        conn.commit()
        return True, "密码修改成功"
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        conn.close()


def reset_password_with_key(username: str, reset_key: str) -> Tuple[bool, str]:
    """管理员重置密钥重置任意用户密码（忘记密码自救）。

    不依赖原密码，但需要正确的 ADMIN_RESET_KEY。
    重置后密码统一为 123456，提示用户登录后立即修改。
    """
    expected = cfg.ADMIN_RESET_KEY
    if not expected:
        return False, "服务端未配置 ADMIN_RESET_KEY，无法使用此功能"
    if not reset_key or reset_key != expected:
        return False, "重置密钥错误"
    _init_db()
    conn = sqlite3.connect(_db_path())
    try:
        cur = conn.execute("SELECT id FROM users WHERE username=?", (username,))
        if not cur.fetchone():
            return False, "用户不存在"
        conn.execute(
            "UPDATE users SET password_hash=? WHERE username=?",
            (_hash_password("123456"), username),
        )
        conn.commit()
        return True, "已将密码重置为 123456，请登录后立即修改"
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        conn.close()