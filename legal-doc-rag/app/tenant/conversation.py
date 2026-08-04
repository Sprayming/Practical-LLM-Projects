"""
Conversation Management for Legal-DOC-RAG.

Provides:
- Conversation CRUD operations
- Message history
- Conversation listing
"""
import sqlite3
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from datetime import datetime
from loguru import logger


def _db_path() -> str:
    """返回 users.db 的路径"""
    base = Path(__file__).resolve().parent.parent.parent
    db_dir = base / "tenant_data"
    db_dir.mkdir(parents=True, exist_ok=True)
    return str(db_dir / "users.db")


def create_conversation(tenant_id: str, user_id: str, title: str = None) -> Tuple[bool, str, int]:
    """
    Create a new conversation.

    Args:
        tenant_id: Tenant ID
        user_id: User ID
        title: Optional conversation title

    Returns:
        Tuple of (success, message, conversation_id)
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
    """
    Add a message to a conversation.

    Args:
        conversation_id: Conversation ID
        role: Message role (user/assistant)
        content: Message content

    Returns:
        Tuple of (success, message)
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
    """
    Get messages for a conversation.

    Args:
        conversation_id: Conversation ID
        limit: Maximum number of messages to return

    Returns:
        List of message dictionaries
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
    """
    List conversations for a tenant/user.

    Args:
        tenant_id: Tenant ID
        user_id: Optional user ID to filter by

    Returns:
        List of conversation dictionaries
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
    """
    Update conversation title.

    Args:
        conversation_id: Conversation ID
        title: New title

    Returns:
        Tuple of (success, message)
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
    """
    Delete a conversation and its messages.

    Args:
        conversation_id: Conversation ID

    Returns:
        Tuple of (success, message)
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
    """
    Get conversation statistics for a tenant.

    Args:
        tenant_id: Tenant ID

    Returns:
        Statistics dictionary
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