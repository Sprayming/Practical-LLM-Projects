"""
conversation.py —— 对话会话管理 API 模块

【作用与功能】
本模块为 legal-doc-rag 提供对话会话的 HTTP 接口，负责会话的 CRUD、消息读写、标题更新
与租户级统计。以用户身份隔离数据，是前端问答历史持久化与会话管理的核心接口。

【主要组成】
- `create` / `list_all` / `delete`：会话的创建、列举与删除。
- `get_messages`：获取指定会话的完整消息历史。
- `add_message_to_conversation`：向会话追加一条消息。
- `update_title`：更新会话标题。
- `stats`：获取租户级对话统计数据。
- `CreateConversationRequest` / `AddMessageRequest` / `UpdateTitleRequest`：请求数据模型。

【适用场景】
- 前端在用户提问/模型回答后持久化消息、展示历史会话列表与对话统计。

【依赖关系】
- 上游调用方：对话前端。
- 下游依赖：app.tenant.conversation、app.api.auth。
"""
import os
import sys

# 将项目根目录添加到系统路径中，以便正确导入项目内的其他模块
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, List
# 导入租户对话管理的底层操作函数
from app.tenant.conversation import (
    create_conversation,
    add_message,
    get_conversation_messages,
    list_conversations,
    update_conversation_title,
    delete_conversation,
    get_conversation_stats,
)
from app.api.auth import get_user_from_token, require_user

# 创建 API 路由器实例，统一添加 /api/conversations 前缀，并打上 "conversations" 标签用于文档分类
router = APIRouter(prefix="/api/conversations", tags=["conversations"])


class CreateConversationRequest(BaseModel):
    """
    创建对话请求的数据模型。
    
    属性：
        title (Optional[str]): 对话标题。如果为空，系统通常会在后续根据首条消息自动生成。
    """
    title: Optional[str] = None


class AddMessageRequest(BaseModel):
    """
    添加消息请求的数据模型。
    
    属性：
        role (str): 消息产生者的角色，通常为 "user" (用户) 或 "assistant" (AI助手)。
        content (str): 消息的具体文本内容。
    """
    role: str
    content: str


class UpdateTitleRequest(BaseModel):
    """
    更新对话标题请求的数据模型。
    
    属性：
        title (str): 新的对话标题。
    """
    title: str


# ============================================================
# Conversation Management (对话管理接口)
# ============================================================

@router.post("")
def create(req: CreateConversationRequest, user: dict = Depends(require_user)):
    """
    创建新的对话。
    
    需要用户登录。为当前用户创建一个新的空对话，用于后续的问答交互。
    
    参数：
        req (CreateConversationRequest): 包含可选对话标题的请求体。
        user (dict): 依赖注入获取的当前登录用户信息，用于提取 tenant_id 和 user_id。
        
    异常：
        HTTPException: 如果创建失败，抛出 400 异常。
        
    返回：
        dict: 包含成功标志、操作消息以及新创建的 conversation_id。
    """
    tenant_id = user["tenant_id"]
    user_id = str(user.get("id", ""))
    ok, msg, conversation_id = create_conversation(tenant_id, user_id, req.title)
    if not ok:
        raise HTTPException(400, msg)
    return {"success": True, "message": msg, "conversation_id": conversation_id}


@router.get("")
def list_all(user: dict = Depends(require_user)):
    """
    获取当前用户的所有对话列表。
    
    需要用户登录。返回该用户在当前租户下的所有历史对话概览（通常不包含具体消息详情，以减少负载）。
    
    参数：
        user (dict): 依赖注入获取的当前登录用户信息，用于提取 tenant_id 和 user_id。
        
    返回：
        dict: 包含对话列表 conversations 和总数 total。
    """
    tenant_id = user["tenant_id"]
    user_id = str(user.get("id", ""))
    conversations = list_conversations(tenant_id, user_id)
    return {"conversations": conversations, "total": len(conversations)}


@router.get("/{conversation_id}")
def get_messages(conversation_id: int, user: dict = Depends(require_user)):
    """
    获取指定对话的完整消息历史。
    
    需要用户登录。根据对话 ID 拉取该会话下的所有聊天记录，用于前端渲染上下文。
    
    参数：
        conversation_id (int): 路径参数，目标对话的 ID。
        user (dict): 依赖注入获取的当前登录用户信息。
        
    返回：
        dict: 包含消息列表 messages 和总数 total。
    """
    # 注意：此处未严格校验该 conversation_id 是否属于当前 user，实际生产中应增加归属权校验以防越权访问
    messages = get_conversation_messages(conversation_id)
    return {"messages": messages, "total": len(messages)}


@router.post("/{conversation_id}/messages")
def add_message_to_conversation(conversation_id: int, req: AddMessageRequest, user: dict = Depends(require_user)):
    """
    向指定对话添加一条消息。
    
    需要用户登录。在用户提问或大模型生成回答后，调用此接口将消息持久化到数据库中。
    
    参数：
        conversation_id (int): 路径参数，目标对话的 ID。
        req (AddMessageRequest): 包含角色和消息内容的请求体。
        user (dict): 依赖注入获取的当前登录用户信息。
        
    异常：
        HTTPException: 如果添加失败（如对话不存在），抛出 400 异常。
        
    返回：
        dict: 包含成功标志和操作消息。
    """
    ok, msg = add_message(conversation_id, req.role, req.content)
    if not ok:
        raise HTTPException(400, msg)
    return {"success": True, "message": msg}


@router.put("/{conversation_id}/title")
def update_title(conversation_id: int, req: UpdateTitleRequest, user: dict = Depends(require_user)):
    """
    更新指定对话的标题。
    
    需要用户登录。允许用户手动重命名对话，或系统在首条消息后自动更新标题。
    
    参数：
        conversation_id (int): 路径参数，目标对话的 ID。
        req (UpdateTitleRequest): 包含新标题的请求体。
        user (dict): 依赖注入获取的当前登录用户信息。
        
    异常：
        HTTPException: 如果更新失败，抛出 400 异常。
        
    返回：
        dict: 包含成功标志和操作消息。
    """
    ok, msg = update_conversation_title(conversation_id, req.title)
    if not ok:
        raise HTTPException(400, msg)
    return {"success": True, "message": msg}


@router.delete("/{conversation_id}")
def delete(conversation_id: int, user: dict = Depends(require_user)):
    """
    删除指定的对话及其关联消息。
    
    需要用户登录。根据对话 ID 删除整个会话记录，通常级联删除其下所有消息。
    
    参数：
        conversation_id (int): 路径参数，待删除的对话 ID。
        user (dict): 依赖注入获取的当前登录用户信息。
        
    异常：
        HTTPException: 如果删除失败，抛出 400 异常。
        
    返回：
        dict: 包含成功标志和操作消息。
    """
    ok, msg = delete_conversation(conversation_id)
    if not ok:
        raise HTTPException(400, msg)
    return {"success": True, "message": msg}


@router.get("/stats/summary")
def stats(user: dict = Depends(require_user)):
    """
    获取当前租户的对话统计数据。
    
    需要用户登录。返回租户级别的对话总数、消息总数等聚合统计信息，用于仪表盘展示。
    
    参数：
        user (dict): 依赖注入获取的当前登录用户信息，用于提取 tenant_id。
        
    返回：
        dict: 包含各项对话统计指标的数据字典。
    """
    tenant_id = user["tenant_id"]
    stats = get_conversation_stats(tenant_id)
    return stats
