"""
Webhook API for Legal-DOC-RAG.

Provides endpoints for:
- Webhook management (CRUD)
- Event triggering
- Log viewing
"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel
from typing import Optional, List, Dict
from app.worker.webhook import get_webhook_manager
from app.api.auth import get_user_from_token

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


def _require_admin(authorization: str = Header(...)) -> dict:
    """Require admin role for access."""
    token = authorization.replace("Bearer ", "").strip()
    if not token:
        raise HTTPException(401, "Missing token")
    user = get_user_from_token(token)
    if user.get("role") != "super_admin":
        raise HTTPException(403, "Admin access required")
    return user


class CreateWebhookRequest(BaseModel):
    name: str
    url: str
    events: List[str]
    secret: Optional[str] = None


class UpdateWebhookRequest(BaseModel):
    name: Optional[str] = None
    url: Optional[str] = None
    events: Optional[List[str]] = None
    enabled: Optional[bool] = None


class TriggerEventRequest(BaseModel):
    event_type: str
    payload: Dict


# ============================================================
# Webhook Management
# ============================================================

@router.post("")
def create(req: CreateWebhookRequest, admin: dict = Depends(_require_admin)):
    """创建Webhook"""
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
    """列出Webhook"""
    tenant_id = admin["tenant_id"]
    manager = get_webhook_manager()
    webhooks = manager.list_webhooks(tenant_id)
    return {"webhooks": webhooks, "total": len(webhooks)}


@router.put("/{webhook_id}")
def update(webhook_id: int, req: UpdateWebhookRequest, admin: dict = Depends(_require_admin)):
    """更新Webhook"""
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
    """删除Webhook"""
    tenant_id = admin["tenant_id"]
    manager = get_webhook_manager()
    ok, msg = manager.delete_webhook(webhook_id, tenant_id)
    if not ok:
        raise HTTPException(400, msg)
    return {"success": True, "message": msg}


# ============================================================
# Event Triggering
# ============================================================

@router.post("/trigger")
def trigger_event(req: TriggerEventRequest, admin: dict = Depends(_require_admin)):
    """触发事件"""
    tenant_id = admin["tenant_id"]
    manager = get_webhook_manager()
    triggered = manager.trigger_event(tenant_id, req.event_type, req.payload)
    return {"success": True, "triggered_webhooks": triggered}


# ============================================================
# Logs
# ============================================================

@router.get("/{webhook_id}/logs")
def get_logs(webhook_id: int, limit: int = 50, admin: dict = Depends(_require_admin)):
    """获取Webhook日志"""
    tenant_id = admin["tenant_id"]
    manager = get_webhook_manager()
    logs = manager.get_webhook_logs(webhook_id, tenant_id, limit)
    return {"logs": logs, "total": len(logs)}


# ============================================================
# Event Types
# ============================================================

@router.get("/events/types")
def list_event_types():
    """列出支持的事件类型"""
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
            {"name": "*", "description": "所有事件"},
        ]
    }