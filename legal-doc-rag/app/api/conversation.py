"""
Conversation API for Legal-DOC-RAG.

Provides endpoints for:
- Conversation management (CRUD)
- Message history
- Conversation listing
"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel
from typing import Optional, List
from app.tenant.conversation import (
    create_conversation,
    add_message,
    get_conversation_messages,
    list_conversations,
    update_conversation_title,
    delete_conversation,
    get_conversation_stats,
)
from app.api.auth import get_user_from_token

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


def _require_user(authorization: str = Header(...)) -> dict:
    """Require authenticated user."""
    token = authorization.replace("Bearer ", "").strip()
    if not token:
        raise HTTPException(401, "Missing token")
    return get_user_from_token(token)


class CreateConversationRequest(BaseModel):
    title: Optional[str] = None


class AddMessageRequest(BaseModel):
    role: str
    content: str


class UpdateTitleRequest(BaseModel):
    title: str


# ============================================================
# Conversation Management
# ============================================================

@router.post("")
def create(req: CreateConversationRequest, user: dict = Depends(_require_user)):
    """创建新对话"""
    tenant_id = user["tenant_id"]
    user_id = str(user.get("id", ""))
    ok, msg, conversation_id = create_conversation(tenant_id, user_id, req.title)
    if not ok:
        raise HTTPException(400, msg)
    return {"success": True, "message": msg, "conversation_id": conversation_id}


@router.get("")
def list_all(user: dict = Depends(_require_user)):
    """列出所有对话"""
    tenant_id = user["tenant_id"]
    user_id = str(user.get("id", ""))
    conversations = list_conversations(tenant_id, user_id)
    return {"conversations": conversations, "total": len(conversations)}


@router.get("/{conversation_id}")
def get_messages(conversation_id: int, user: dict = Depends(_require_user)):
    """获取对话消息历史"""
    messages = get_conversation_messages(conversation_id)
    return {"messages": messages, "total": len(messages)}


@router.post("/{conversation_id}/messages")
def add_message_to_conversation(conversation_id: int, req: AddMessageRequest, user: dict = Depends(_require_user)):
    """添加消息到对话"""
    ok, msg = add_message(conversation_id, req.role, req.content)
    if not ok:
        raise HTTPException(400, msg)
    return {"success": True, "message": msg}


@router.put("/{conversation_id}/title")
def update_title(conversation_id: int, req: UpdateTitleRequest, user: dict = Depends(_require_user)):
    """更新对话标题"""
    ok, msg = update_conversation_title(conversation_id, req.title)
    if not ok:
        raise HTTPException(400, msg)
    return {"success": True, "message": msg}


@router.delete("/{conversation_id}")
def delete(conversation_id: int, user: dict = Depends(_require_user)):
    """删除对话"""
    ok, msg = delete_conversation(conversation_id)
    if not ok:
        raise HTTPException(400, msg)
    return {"success": True, "message": msg}


@router.get("/stats/summary")
def stats(user: dict = Depends(_require_user)):
    """获取对话统计"""
    tenant_id = user["tenant_id"]
    stats = get_conversation_stats(tenant_id)
    return stats