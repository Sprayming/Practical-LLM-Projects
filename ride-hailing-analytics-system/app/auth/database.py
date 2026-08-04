import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Optional
from loguru import logger
import hashlib
import secrets


DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "users.db"


def get_user_db():
    """获取用户数据库连接"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_user_db():
    """初始化用户数据库表"""
    conn = get_user_db()
    cursor = conn.cursor()
    
    # 创建用户表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            hashed_password TEXT NOT NULL,
            full_name TEXT,
            is_active BOOLEAN DEFAULT 1,
            is_admin BOOLEAN DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP
        )
    """)
    
    # 创建API密钥表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS api_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            api_key TEXT UNIQUE NOT NULL,
            name TEXT,
            is_active BOOLEAN DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_used TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    """)
    
    conn.commit()
    conn.close()
    logger.info("用户数据库初始化完成")


def hash_password(password: str) -> str:
    """哈希密码"""
    salt = secrets.token_hex(16)
    password_hash = hashlib.sha256((password + salt).encode()).hexdigest()
    return f"{salt}:{password_hash}"


def verify_password(password: str, hashed_password: str) -> bool:
    """验证密码"""
    try:
        salt, password_hash = hashed_password.split(":")
        return hashlib.sha256((password + salt).encode()).hexdigest() == password_hash
    except Exception:
        return False


def create_user(username: str, email: str, password: str, full_name: str = None) -> Optional[dict]:
    """创建用户"""
    conn = get_user_db()
    cursor = conn.cursor()
    
    try:
        # 检查用户名是否已存在
        cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
        if cursor.fetchone():
            return None
        
        # 检查邮箱是否已存在
        cursor.execute("SELECT id FROM users WHERE email = ?", (email,))
        if cursor.fetchone():
            return None
        
        # 创建用户
        hashed_password = hash_password(password)
        cursor.execute(
            "INSERT INTO users (username, email, hashed_password, full_name) VALUES (?, ?, ?, ?)",
            (username, email, hashed_password, full_name)
        )
        conn.commit()
        
        user_id = cursor.lastrowid
        return {
            "id": user_id,
            "username": username,
            "email": email,
            "full_name": full_name,
            "is_active": True,
            "is_admin": False,
            "created_at": datetime.now(),
            "last_login": None
        }
    except Exception as e:
        logger.error("创建用户失败: {}", e)
        conn.rollback()
        return None
    finally:
        conn.close()


def get_user_by_username(username: str) -> Optional[dict]:
    """根据用户名获取用户"""
    conn = get_user_db()
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
        row = cursor.fetchone()
        
        if row:
            return {
                "id": row["id"],
                "username": row["username"],
                "email": row["email"],
                "full_name": row["full_name"],
                "is_active": bool(row["is_active"]),
                "is_admin": bool(row["is_admin"]),
                "created_at": row["created_at"],
                "last_login": row["last_login"]
            }
        return None
    finally:
        conn.close()


def get_user_by_id(user_id: int) -> Optional[dict]:
    """根据用户ID获取用户"""
    conn = get_user_db()
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        
        if row:
            return {
                "id": row["id"],
                "username": row["username"],
                "email": row["email"],
                "full_name": row["full_name"],
                "is_active": bool(row["is_active"]),
                "is_admin": bool(row["is_admin"]),
                "created_at": row["created_at"],
                "last_login": row["last_login"]
            }
        return None
    finally:
        conn.close()


def authenticate_user(username: str, password: str) -> Optional[dict]:
    """验证用户身份"""
    user = get_user_by_username(username)
    
    if not user:
        return None
    
    # 获取密码哈希
    conn = get_user_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT hashed_password FROM users WHERE username = ?", (username,))
        row = cursor.fetchone()
        if not row:
            return None
        
        if verify_password(password, row["hashed_password"]):
            # 更新最后登录时间
            cursor.execute(
                "UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE username = ?",
                (username,)
            )
            conn.commit()
            return user
        return None
    finally:
        conn.close()


def create_api_key(user_id: int, name: str = None) -> Optional[str]:
    """创建API密钥"""
    conn = get_user_db()
    cursor = conn.cursor()
    
    try:
        api_key = f"rh_{secrets.token_hex(32)}"
        cursor.execute(
            "INSERT INTO api_keys (user_id, api_key, name) VALUES (?, ?, ?)",
            (user_id, api_key, name)
        )
        conn.commit()
        return api_key
    except Exception as e:
        logger.error("创建API密钥失败: {}", e)
        return None
    finally:
        conn.close()


def validate_api_key(api_key: str) -> Optional[int]:
    """验证API密钥，返回用户ID"""
    conn = get_user_db()
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            "SELECT user_id FROM api_keys WHERE api_key = ? AND is_active = 1",
            (api_key,)
        )
        row = cursor.fetchone()
        
        if row:
            # 更新最后使用时间
            cursor.execute(
                "UPDATE api_keys SET last_used = CURRENT_TIMESTAMP WHERE api_key = ?",
                (api_key,)
            )
            conn.commit()
            return row["user_id"]
        return None
    finally:
        conn.close()


# 初始化数据库
init_user_db()