"""
webhook.py —— Webhook 事件通知管理 API 模块

【作用与功能】
本模块为 legal-doc-rag 提供 Webhook 的 HTTP 管理接口，支持 Webhook 配置的 CRUD、手动
触发事件、查看调用日志与系统支持的事件类型。通过超级管理员权限依赖隔离，用于把平台内
事件(如文档上传、对话完成)异步通知到外部系统。

【主要组成】
- `_require_admin`:超级管理员权限依赖。
- `create` / `list_all` / `update` / `delete`:Webhook 配置的增、查、改、删。
- `trigger_event`:手动触发指定事件并通知已订阅 Webhook。
- `get_logs`:查看某 Webhook 的最近调用日志。
- `list_event_types`:列出系统支持的预置事件类型。
- `CreateWebhookRequest` / `UpdateWebhookRequest` / `TriggerEventRequest`:请求数据模型。

【适用场景】
- 管理员配置事件回调，在文档上传完成/对话结束等节点通知外部系统(如企业微信、自建服务)。

【依赖关系】
- 上游调用方:管理后台前端。
- 下游依赖:app.worker.webhook(get_webhook_manager)、app.api.auth。
"""
import os
import sys

# 将项目根目录添加到系统路径中，以便正确导入项目内的其他模块
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel
from typing import Optional, List, Dict
from app.worker.webhook import get_webhook_manager
from app.api.auth import get_user_from_token

# 创建 API 路由器实例，统一添加 /api/webhooks 前缀，并打上 "webhooks" 标签用于文档分类
router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


def _require_admin(authorization: str = Header(...)) -> dict:
    """
    依赖注入函数:校验请求是否具有超级管理员权限。
    
    从请求头提取 Authorization Token，验证用户身份，并检查其角色是否为 super_admin。
    如果不是管理员或 Token 无效，则抛出 HTTP 异常阻断请求。
    
    参数:
        authorization (str): 请求头中的 Authorization 字段值，预期格式为 "Bearer <token>"。
        
    异常:
        HTTPException: 如果缺少 Token 抛出 401 异常；如果用户不是超级管理员抛出 403 异常。
        
    返回:
        dict: 验证通过后的当前用户信息字典。
    """
    # 去除 "Bearer " 前缀，提取纯 Token 字符串
    token = authorization.replace("Bearer ", "").strip()
    if not token:
        raise HTTPException(401, "Missing token")
    user = get_user_from_token(token)
    # 权限校验:仅允许 super_admin 角色访问
    if user.get("role") != "super_admin":
        raise HTTPException(403, "Admin access required")
    return user


class CreateWebhookRequest(BaseModel):
    """
    创建 Webhook 请求的数据模型。
    
    属性:
        name (str): Webhook 名称，用于标识和管理。
        url (str): Webhook 接收通知的目标 URL。
        events (List[str]): 监听的事件类型列表(如 "document.uploaded")。
        secret (Optional[str]): 可选的签名密钥，用于验证请求来源。
    """
    name: str
    url: str
    events: List[str]
    secret: Optional[str] = None


class UpdateWebhookRequest(BaseModel):
    """
    更新 Webhook 请求的数据模型。
    
    所有字段均为可选，允许部分更新。
    
    属性:
        name (Optional[str]): 新的 Webhook 名称。
        url (Optional[str]): 新的目标 URL。
        events (Optional[List[str]]): 新的事件监听列表。
        enabled (Optional[bool]): 是否启用该 Webhook。
    """
    name: Optional[str] = None
    url: Optional[str] = None
    events: Optional[List[str]] = None
    enabled: Optional[bool] = None


class TriggerEventRequest(BaseModel):
    """
    手动触发事件请求的数据模型。
    
    属性:
        event_type (str): 要触发的事件类型。
        payload (Dict): 事件的具体数据负载(JSON 格式)。
    """
    event_type: str
    payload: Dict


# ============================================================
# Webhook Management (Webhook 管理接口)
# ============================================================

@router.post("")
def create(req: CreateWebhookRequest, admin: dict = Depends(_require_admin)):
    """
    创建新的 Webhook 配置。
    
    需要超级管理员权限。为指定租户创建新的 Webhook，用于监听特定事件并异步通知外部系统。
    
    参数:
        req (CreateWebhookRequest): 包含 Webhook 配置的请求体。
        admin (dict): 依赖注入获取的当前管理员信息，用于提取 tenant_id。
        
    异常:
        HTTPException: 如果创建失败(如 URL 无效或事件类型不支持)，抛出 400 异常。
        
    返回:
        dict: 包含成功标志、消息和新建的 webhook_id。
    """
    tenant_id = admin["tenant_id"]
    manager = get_webhook_manager()
    ok, msg, webhook_id = manager.create_webhook(
        tenant_id, req.name, req.url, req.events, req.secret
    )
    if not ok:
        raise HTTPException(400, msg)
    return {"success": True, "message": msg, "webhook_id": webhook_id}


@router.get("")
def list_all(admin: dict = Depends(_require_admin)):
    """
    获取指定租户的所有 Webhook 列表。
    
    需要超级管理员权限。返回该租户下所有已配置的 Webhook 信息。
    
    参数:
        admin (dict): 依赖注入获取的当前管理员信息，用于提取 tenant_id。
        
    返回:
        dict: 包含 Webhook 列表 webhooks 和总数 total。
    """
    tenant_id = admin["tenant_id"]
    manager = get_webhook_manager()
    webhooks = manager.list_webhooks(tenant_id)
    return {"webhooks": webhooks, "total": len(webhooks)}


@router.put("/{webhook_id}")
def update(webhook_id: int, req: UpdateWebhookRequest, admin: dict = Depends(_require_admin)):
    """
    更新现有 Webhook 的配置。
    
    需要超级管理员权限。允许部分更新 Webhook 的各项属性。
    
    参数:
        webhook_id (int): 路径参数，待更新的 Webhook ID。
        req (UpdateWebhookRequest): 包含更新内容的请求体。
        admin (dict): 依赖注入获取的当前管理员信息，用于提取 tenant_id。
        
    异常:
        HTTPException: 如果更新失败(如 Webhook 不存在)，抛出 400 异常。
        
    返回:
        dict: 包含成功标志和操作消息。
    """
    tenant_id = admin["tenant_id"]
    manager = get_webhook_manager()
    ok, msg = manager.update_webhook(
        webhook_id, tenant_id, req.name, req.url, req.events, req.enabled
    )
    if not ok:
        raise HTTPException(400, msg)
    return {"success": True, "message": msg}


@router.delete("/{webhook_id}")
def delete(webhook_id: int, admin: dict = Depends(_require_admin)):
    """
    删除指定的 Webhook 配置。
    
    需要超级管理员权限。删除后该 Webhook 将不再接收事件通知。
    
    参数:
        webhook_id (int): 路径参数，待删除的 Webhook ID。
        admin (dict): 依赖注入获取的当前管理员信息，用于提取 tenant_id。
        
    异常:
        HTTPException: 如果删除失败(如 Webhook 不存在)，抛出 400 异常。
        
    返回:
        dict: 包含成功标志和操作消息。
    """
    tenant_id = admin["tenant_id"]
    manager = get_webhook_manager()
    ok, msg = manager.delete_webhook(webhook_id, tenant_id)
    if not ok:
        raise HTTPException(400, msg)
    return {"success": True, "message": msg}


# ============================================================
# Event Triggering (事件触发接口)
# ============================================================

@router.post("/trigger")
def trigger_event(req: TriggerEventRequest, admin: dict = Depends(_require_admin)):
    """
    手动触发指定事件。
    
    需要超级管理员权限。用于测试或主动通知外部系统特定事件的发生。
    
    参数:
        req (TriggerEventRequest): 包含事件类型和负载的请求体。
        admin (dict): 依赖注入获取的当前管理员信息，用于提取 tenant_id。
        
    返回:
        dict: 包含成功标志和成功触发的 Webhook 列表。
    """
    tenant_id = admin["tenant_id"]
    manager = get_webhook_manager()
    triggered = manager.trigger_event(tenant_id, req.event_type, req.payload)
    return {"success": True, "triggered_webhooks": triggered}


# ============================================================
# Logs (日志查看接口)
# ============================================================

@router.get("/{webhook_id}/logs")
def get_logs(webhook_id: int, limit: int = 50, admin: dict = Depends(_require_admin)):
    """
    获取指定 Webhook 的调用日志。
    
    需要超级管理员权限。返回该 Webhook 最近的通知历史，便于排查问题。
    
    参数:
        webhook_id (int): 路径参数，目标 Webhook 的 ID。
        limit (int): 查询参数，返回的最大日志条数，默认为 50。
        admin (dict): 依赖注入获取的当前管理员信息，用于提取 tenant_id。
        
    返回:
        dict: 包含日志列表 logs 和总数 total。
    """
    tenant_id = admin["tenant_id"]
    manager = get_webhook_manager()
    logs = manager.get_webhook_logs(webhook_id, tenant_id, limit)
    return {"logs": logs, "total": len(logs)}


# ============================================================
# Event Types (事件类型接口)
# ============================================================

@router.get("/events/types")
def list_event_types():
    """
    获取系统支持的所有事件类型列表。
    
    无需权限验证。用于前端展示可选事件类型，方便管理员配置 Webhook 监听。
    
    返回:
        dict: 包含事件类型列表 event_types，每个类型包含名称和描述。
    """
    from app.worker.webhook import WebhookEvents
    return {
        "event_types": [
            {"name": "document.uploaded", "description": "文档上传完成"},
            {"name": "document.deleted", "description": "文档删除"},
            {"name": "chat.completed", "description": "对话完成"},
            {"name": "user.registered", "description": "用户注册"},
            {"name": "user.deleted", "description": "用户删除"},
            {"name": "experiment.started", "description": "实验启动"},
            {"name": "experiment.stopped", "description": "实验停止"},
            {"name": "system.error", "description": "系统错误"},
        ]
    }
