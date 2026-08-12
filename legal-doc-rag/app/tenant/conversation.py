"""
conversation.py —— Legal-DOC-rag 对话与消息历史管理

【作用与功能】
本模块负责多轮对话及其消息历史的持久化与查询，支撑聊天界面的会话列表、
历史回溯与统计。对话(conversations 表)按租户/用户隔离，消息
(conversation_messages 表，外键级联删除)记录 role 与 content，从而支持
上下文重建与用量统计。底层使用 users.db 的相关表。

【主要组成】
- `_db_path`:users.db 路径
- `create_conversation` / `list_conversations`:对话的创建与列表
- `add_message` / `get_conversation_messages`:消息的写入与按时间读取
- `update_conversation_title` / `delete_conversation`:标题维护与删除
- `get_conversation_stats`:租户级对话/消息统计

【适用场景】
- 场景1:用户发起或继续一次法律问答会话
- 场景2:前端展示会话列表与历史消息、查看使用统计

【依赖关系】
- 上游调用方:聊天路由、会话管理接口、统计看板
- 下游依赖:sqlite3、users.db(conversations/conversation_messages 表)
"""
import sqlite3
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from datetime import datetime
from loguru import logger


def _db_path() -> str:
    """返回 users.db 的磁盘路径(位于项目根的 tenant_data 目录)。

    参数:
        无

    返回:
        str: users.db 的绝对路径

    异常:
        无
    适用场景:
        - 所有对话数据操作前获取统一存储路径
    """
    base = Path(__file__).resolve().parent.parent.parent
    db_dir = base / "tenant_data"
    db_dir.mkdir(parents=True, exist_ok=True)
    return str(db_dir / "users.db")


def create_conversation(tenant_id: str, user_id: str, title: str = None) -> Tuple[bool, str, int]:
    """创建一条新对话。

    写入 conversations 表；未提供标题时自动以当前时间生成(如「对话 08-12 14:30」)，
    返回新建的 conversation_id。

    参数:
        tenant_id (str): 租户标识
        user_id (str): 用户标识
        title (str, 可选): 对话标题；省略时自动生成

    返回:
        Tuple[bool, str, int]: (成功, 消息, 新建对话 id)

    异常:
        无(数据库错误被捕获并回滚)
    适用场景:
        - 用户发起新的问答会话
    """
    conn = sqlite3.connect(_db_path())
    try:
        cur = conn.execute(
            "INSERT INTO conversations (tenant_id, user_id, title) VALUES (?, ?, ?)",
            (tenant_id, user_id, title or f"对话 {datetime.now().strftime('%m-%d %H:%M')}")
        )
        conversation_id = cur.lastrowid
        conn.commit()
        return True, "对话创建成功", conversation_id
    except Exception as e:
        conn.rollback()
        return False, str(e), 0
    finally:
        conn.close()


def add_message(conversation_id: int, role: str, content: str) -> Tuple[bool, str]:
    """向对话追加一条消息，并刷新对话更新时间。

    在 conversation_messages 表写入 (conversation_id, role, content)，同时
    更新所属 conversations 的 updated_at，便于会话列表按最近活跃排序。

    参数:
        conversation_id (int): 目标对话 id
        role (str): 消息角色，如 "user" / "assistant"
        content (str): 消息内容

    返回:
        Tuple[bool, str]: (是否成功, 消息)

    异常:
        无(数据库错误被捕获并回滚)
    适用场景:
        - 聊天时记录用户提问与 AI 回答
    """
    conn = sqlite3.connect(_db_path())
    try:
        conn.execute(
            "INSERT INTO conversation_messages (conversation_id, role, content) VALUES (?, ?, ?)",
            (conversation_id, role, content)
        )
        # Update conversation timestamp
        conn.execute(
            "UPDATE conversations SET updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (conversation_id,)
        )
        conn.commit()
        return True, "消息添加成功"
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        conn.close()


def get_conversation_messages(conversation_id: int, limit: int = 50) -> List[Dict]:
    """获取某对话的消息列表(按时间正序)。

    按 id 降序取最近 `limit` 条后再逆转为时间正序，便于直接作为上下文喂给
    模型；每条含 id、role、content、created_at。

    参数:
        conversation_id (int): 目标对话 id
        limit (int): 返回消息数上限，默认 50

    返回:
        List[Dict]: 时间正序的消息字典列表

    异常:
        无
    适用场景:
        - 加载历史消息以重建会话上下文
    """
    conn = sqlite3.connect(_db_path())
    try:
        cur = conn.execute(
            """SELECT id, role, content, created_at
               FROM conversation_messages
               WHERE conversation_id=?
               ORDER BY id DESC
               LIMIT ?""",
            (conversation_id, limit)
        )
        rows = cur.fetchall()
        # Reverse to get chronological order
        rows.reverse()
        return [
            {
                "id": row[0],
                "role": row[1],
                "content": row[2],
                "created_at": row[3],
            }
            for row in rows
        ]
    finally:
        conn.close()


def list_conversations(tenant_id: str, user_id: str = None) -> List[Dict]:
    """列出某租户(或某用户)的对话。

    按 updated_at 倒序返回对话列表；提供 `user_id` 时仅返回该用户的对话。
    每条含 id、title、created_at、updated_at。

    参数:
        tenant_id (str): 租户标识
        user_id (str, 可选): 用户标识；提供则按用户过滤

    返回:
        List[Dict]: 对话字典列表(最新活跃在前)

    异常:
        无
    适用场景:
        - 会话列表页展示
    """
    conn = sqlite3.connect(_db_path())
    try:
        if user_id:
            cur = conn.execute(
                """SELECT id, title, created_at, updated_at
                   FROM conversations
                   WHERE tenant_id=? AND user_id=?
                   ORDER BY updated_at DESC""",
                (tenant_id, user_id)
            )
        else:
            cur = conn.execute(
                """SELECT id, title, created_at, updated_at
                   FROM conversations
                   WHERE tenant_id=?
                   ORDER BY updated_at DESC""",
                (tenant_id,)
            )

        rows = cur.fetchall()
        return [
            {
                "id": row[0],
                "title": row[1],
                "created_at": row[2],
                "updated_at": row[3],
            }
            for row in rows
        ]
    finally:
        conn.close()


def update_conversation_title(conversation_id: int, title: str) -> Tuple[bool, str]:
    """更新对话标题。

    按 conversation_id 将 title 字段更新为新值。

    参数:
        conversation_id (int): 目标对话 id
        title (str): 新标题

    返回:
        Tuple[bool, str]: (是否成功, 消息)

    异常:
        无(数据库错误被捕获并回滚)
    适用场景:
        - 用户重命名会话
    """
    conn = sqlite3.connect(_db_path())
    try:
        conn.execute(
            "UPDATE conversations SET title=? WHERE id=?",
            (title, conversation_id)
        )
        conn.commit()
        return True, "标题更新成功"
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        conn.close()


def delete_conversation(conversation_id: int) -> Tuple[bool, str]:
    """删除对话及其全部消息。

    先删除 conversation_messages 中的消息(外键级联亦可)，再删除
    conversations 主记录，确保无孤儿消息残留。

    参数:
        conversation_id (int): 目标对话 id

    返回:
        Tuple[bool, str]: (是否成功, 消息)

    异常:
        无(数据库错误被捕获并回滚)
    适用场景:
        - 用户删除会话
    """
    conn = sqlite3.connect(_db_path())
    try:
        # Delete messages first
        conn.execute(
            "DELETE FROM conversation_messages WHERE conversation_id=?",
            (conversation_id,)
        )
        # Delete conversation
        conn.execute(
            "DELETE FROM conversations WHERE id=?",
            (conversation_id,)
        )
        conn.commit()
        return True, "对话删除成功"
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        conn.close()


def get_conversation_stats(tenant_id: str) -> Dict:
    """统计某租户的对话与消息使用情况。

    计算总对话数、总消息数，并据此得出每对话平均消息数(无对话时为 0)，
    用于用量看板展示。

    参数:
        tenant_id (str): 租户标识

    返回:
        Dict: 含 total_conversations、total_messages、avg_messages_per_conversation

    异常:
        无
    适用场景:
        - 管理后台/用量统计面板
    """
    conn = sqlite3.connect(_db_path())
    try:
        # Total conversations
        cur = conn.execute(
            "SELECT COUNT(*) FROM conversations WHERE tenant_id=?",
            (tenant_id,)
        )
        total_conversations = cur.fetchone()[0]

        # Total messages
        cur = conn.execute(
            """SELECT COUNT(*) FROM conversation_messages cm
               JOIN conversations c ON cm.conversation_id = c.id
               WHERE c.tenant_id=?""",
            (tenant_id,)
        )
        total_messages = cur.fetchone()[0]

        # Average messages per conversation
        avg_messages = total_messages / total_conversations if total_conversations > 0 else 0

        return {
            "total_conversations": total_conversations,
            "total_messages": total_messages,
            "avg_messages_per_conversation": round(avg_messages, 2),
        }
    finally:
        conn.close()