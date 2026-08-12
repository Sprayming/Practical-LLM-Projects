"""
auth.py —— Legal-DOC-RAG 用户、租户与鉴权模块

【作用与功能】
本模块负责系统的身份与多租户基础:基于 SQLite(users.db)管理用户账户、
租户归属、角色(super_admin/user)、密码安全(PBKDF2-HMAC-SHA256 加盐哈希)，
并提供注册、登录、用户列表/删除、角色调整、改密以及管理员密钥重置密码等
能力。注册首个用户自动成为 super_admin，其余为普通 user。

【主要组成】
- `_db_path` / `_init_db`:users.db 路径与建表(users/tenants/文档分类/文档/对话/消息)
- `_hash_password` / `_verify_password`:密码加盐哈希与校验
- `register` / `login` / `has_users`:注册、登录与是否已有用户
- `list_users` / `delete_user` / `set_user_role`:管理后台用户治理
- `change_password` / `reset_password_with_key`:密码修改与密钥重置

【适用场景】
- 场景1:登录/注册接口调用 `login` / `register`
- 场景2:管理后台治理用户与权限
- 场景3:忘记密码时由管理员用 `ADMIN_RESET_KEY` 重置

【依赖关系】
- 上游调用方:鉴权路由、管理后台、依赖注入
- 下游依赖:app.core.config(ADMIN_RESET_KEY)、sqlite3
"""
import os
import hashlib
import secrets
import sqlite3
from pathlib import Path
from typing import Optional, Tuple, Dict, List

import app.core.config as cfg


def _db_path() -> str:
    """返回 users.db 的磁盘路径(位于项目根的 tenant_data 目录)。

    参数:
        无

    返回:
        str: users.db 的绝对路径

    异常:
        无(目录创建失败时由调用方抛错)
    适用场景:
        - 所有用户/租户数据库操作前获取统一存储路径
    """
    base = Path(__file__).resolve().parent.parent.parent
    db_dir = base / "tenant_data"
    db_dir.mkdir(parents=True, exist_ok=True)
    return str(db_dir / "users.db")


def _init_db():
    """初始化用户/租户相关数据库表。

    幂等创建 users、tenants、document_categories、documents、conversations、
    conversation_messages 六张表，并将遗留的 `admin` 角色迁移为 `super_admin`。
    可在每次操作前安全调用。

    参数:
        无

    返回:
        None

    异常:
        无(sqlite 错误向上抛出由调用方处理)
    适用场景:
        - 各业务函数执行 SQL 前确保表存在
    """
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
    # 文档表(用于存储文档元数据和分类)
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
    """将明文密码通过 PBKDF2-HMAC-SHA256 加盐哈希。

    生成 16 字节随机盐，迭代 100000 次，返回 `盐$哈希` 形式字符串，便于
    后续校验时拆出盐值重用。

    参数:
        password (str): 明文密码

    返回:
        str: `salt$hash`(十六进制)格式的存储串

    异常:
        无
    适用场景:
        - 注册、改密、密钥重置时生成安全存储串
    """
    salt = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100000)
    return salt + "$" + h.hex()


def _verify_password(password: str, stored: str) -> bool:
    """校验明文密码与存储哈希是否匹配。

    从 `salt$hash` 中拆出盐值，对输入密码做相同哈希后与存储哈希比对。

    参数:
        password (str): 待校验的明文密码
        stored (str): 数据库中 `salt$hash` 格式的存储串

    返回:
        bool: 匹配为 True，否则 False

    异常:
        无(拆分/编码错误由调用方上下文决定；此处假设格式正确)
    适用场景:
        - 登录、改密原密码校验
    """
    salt, h = stored.split("$")
    v = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100000)
    return h == v.hex()


def register(username: str, password: str) -> Tuple[bool, str]:
    """注册新用户并同时创建其专属租户。

    先查重用户名；通过后生成 8 字符租户 ID 并写入 tenants 表，再写入 users
    表——首个注册用户自动获得 `super_admin` 角色，其余为 `user`。返回
    (成功, 消息含租户 ID)。

    参数:
        username (str): 用户名
        password (str): 明文密码(入库前加盐哈希)

    返回:
        Tuple[bool, str]: (是否成功, 消息/错误信息)

    异常:
        无(数据库错误被捕获并回滚，返回 (False, 错误字符串))
    适用场景:
        - 注册接口受理新用户
    """
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
    """用户登录校验。

    按用户名查用户，校验密码哈希；任一不匹配或用户不存在均返回
    (False, {"error": "用户名或密码错误"})。成功则返回 (True, 用户信息字典)。

    参数:
        username (str): 用户名
        password (str): 明文密码

    返回:
        Tuple[bool, Optional[Dict]]: (成功, 用户信息 / 错误字典)

    异常:
        无(仅查询，数据库错误由 finally 关闭连接)
    适用场景:
        - 登录接口验证凭据
    """
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
    """检查系统中是否已存在任何用户。

    用于判断是否需要初始化(如首个用户应为 super_admin)，以及是否展示
    注册入口。

    参数:
        无

    返回:
        bool: 存在用户为 True，否则 False

    异常:
        无
    适用场景:
        - 启动/登录页判断系统是否已初始化
    """
    _init_db()
    conn = sqlite3.connect(_db_path())
    try:
        cur = conn.execute("SELECT COUNT(*) FROM users")
        return cur.fetchone()[0] > 0
    finally:
        conn.close()


def list_users() -> List[Dict]:
    """列出全部用户(供管理后台使用)。

    按 id 升序读取 users 表，返回含 user_id、用户名、租户 ID、角色与创建
    时间的字典列表。

    参数:
        无

    返回:
        List[Dict]: 用户字典列表

    异常:
        无
    适用场景:
        - 管理后台用户列表展示
    """
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
    """删除指定用户。

    按用户名删除 users 表记录，返回是否实际删除了行(rowcount > 0)。

    参数:
        username (str): 待删除的用户名

    返回:
        bool: 实际删除成功为 True，否则 False

    异常:
        无(数据库错误由 finally 关闭连接)
    适用场景:
        - 管理后台移除用户
    """
    _init_db()
    conn = sqlite3.connect(_db_path())
    try:
        cur = conn.execute("DELETE FROM users WHERE username=?", (username,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def set_user_role(username: str, role: str) -> Tuple[bool, str]:
    """修改用户角色(super_admin / user)，用于管理后台提权/降级。

    先校验角色取值合法，再确认用户存在，之后更新其 role 字段。

    参数:
        username (str): 目标用户名
        role (str): 新角色，仅允许 "super_admin" 或 "user"

    返回:
        Tuple[bool, str]: (是否成功, 消息)

    异常:
        无(数据库错误被捕获并回滚)
    适用场景:
        - 管理后台调整用户权限
    """
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
    """修改密码，需先校验原密码。

    确认用户存在且原密码正确，再校验新密码非空且至少 6 位，通过后以新哈希
    覆盖旧值。

    参数:
        username (str): 用户名
        old_password (str): 原明文密码(用于校验)
        new_password (str): 新明文密码(入库前哈希)

    返回:
        Tuple[bool, str]: (是否成功, 消息)

    异常:
        无(数据库错误被捕获并回滚)
    适用场景:
        - 用户主动改密
    """
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
    """管理员用重置密钥重置任意用户密码(忘记密码自救)。

    不依赖原密码，但需要正确的 `ADMIN_RESET_KEY`(来自配置)。校验通过后
    将该用户密码统一重置为 `123456`，并提示登录后立即修改。

    参数:
        username (str): 目标用户名
        reset_key (str): 管理员重置密钥，需等于 cfg.ADMIN_RESET_KEY

    返回:
        Tuple[bool, str]: (是否成功, 消息)

    异常:
        无(数据库错误被捕获并回滚)
    适用场景:
        - 管理员代为重置忘记密码的账号
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