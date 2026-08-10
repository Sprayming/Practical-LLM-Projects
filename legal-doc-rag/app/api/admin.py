"""
Admin API for Legal-DOC-RAG.

Provides endpoints for:
- User management (list, delete users)
- System statistics
- Configuration management
"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel
from typing import Optional
import app.core.config as cfg
from app.api.auth import get_user_from_token
from app.tenant.auth import has_users, list_users as list_users_db, delete_user, set_user_role as set_user_role_db

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _require_admin(authorization: str = Header(...)) -> dict:
    """Require admin role for access."""
    token = authorization.replace("Bearer ", "").strip()
    if not token:
        raise HTTPException(401, "Missing token")
    user = get_user_from_token(token)
    if user.get("role") != "super_admin":
        raise HTTPException(403, "Admin access required")
    return user


# ============================================================
# User Management
# ============================================================

@router.get("/users")
def list_users(admin: dict = Depends(_require_admin)):
    """List all users (admin only)."""
    users = list_users_db()
    return {"users": users, "total": len(users)}


class DeleteUserRequest(BaseModel):
    username: str


class SetRoleRequest(BaseModel):
    role: str  # "super_admin" | "user"


@router.put("/users/{username}/role")
def update_user_role(
    username: str, req: SetRoleRequest, admin: dict = Depends(_require_admin)
):
    """手动设置用户角色：提权为超级管理员 / 降级为普通用户。

    - 不允许修改自己的角色（避免误操作锁死权限）。
    - 提权为超级管理员时受 cfg.MAX_SUPER_ADMINS 名额上限限制。
    """
    if username == admin.get("username"):
        raise HTTPException(400, "不能修改自己的角色")
    if req.role not in ("super_admin", "user"):
        raise HTTPException(400, "无效的角色")

    # 名额校验：提权为超级管理员时检查上限
    if req.role == "super_admin":
        users = list_users_db()
        current = sum(1 for u in users if u.get("role") == "super_admin")
        if current >= cfg.MAX_SUPER_ADMINS:
            raise HTTPException(
                403, f"超级管理员名额已满（最多 {cfg.MAX_SUPER_ADMINS} 个）"
            )

    ok, msg = set_user_role_db(username, req.role)
    if not ok:
        raise HTTPException(404 if "不存在" in msg else 400, msg)
    return {"success": True, "message": msg}


@router.delete("/users/{username}")
def delete_user(username: str, admin: dict = Depends(_require_admin)):
    """Delete a user (admin only)."""
    # Prevent deleting yourself
    if username == admin.get("username"):
        raise HTTPException(400, "Cannot delete yourself")

    ok = delete_user(username)
    if not ok:
        raise HTTPException(404, "User not found")

    return {"success": True, "message": f"User '{username}' deleted"}


# ============================================================
# System Statistics
# ============================================================

@router.get("/stats")
def get_stats(admin: dict = Depends(_require_admin)):
    """Get system statistics (admin only)."""
    from app.observability.monitoring import get_metrics_collector
    from app.observability.tracker import get_trace_store

    collector = get_metrics_collector()
    trace_store = get_trace_store()

    # User stats
    users = list_users_db()
    user_count = len(users)
    admin_count = sum(1 for u in users if u.get("role") == "super_admin")

    # Document stats
    import os
    doc_count = 0
    upload_dir = cfg.UPLOAD_DIR
    if os.path.exists(upload_dir):
        for tenant_dir in os.listdir(upload_dir):
            tenant_path = os.path.join(upload_dir, tenant_dir)
            if os.path.isdir(tenant_path):
                doc_count += len([f for f in os.listdir(tenant_path) if f.endswith(".pdf")])

    # ChromaDB stats
    vector_count = 0
    chroma_dir = cfg.CHROMA_PERSIST_DIR
    if os.path.exists(chroma_dir):
        for tenant_dir in os.listdir(chroma_dir):
            tenant_path = os.path.join(chroma_dir, tenant_dir)
            if os.path.isdir(tenant_path):
                try:
                    import chromadb
                    client = chromadb.PersistentClient(path=tenant_path)
                    for col in client.list_collections():
                        vector_count += col.count()
                except Exception:
                    pass

    # Metrics
    metrics = collector.to_dict()
    traces = trace_store.summary()

    return {
        "users": {"total": user_count, "admins": admin_count},
        "documents": {"total": doc_count},
        "vectors": {"total": vector_count},
        "metrics": metrics,
        "traces": traces,
    }


# ============================================================
# Configuration
# ============================================================

@router.get("/config")
def get_config(admin: dict = Depends(_require_admin)):
    """Get current configuration (admin only)."""
    return {
        "llm_model": cfg.LLM_MODEL,
        "llm_base_url": cfg.LLM_BASE_URL,
        "embedding_model": cfg.EMBEDDING_MODEL,
        "embedding_type": cfg.EMBEDDER_TYPE,
        "chroma_persist_dir": cfg.CHROMA_PERSIST_DIR,
        "upload_dir": cfg.UPLOAD_DIR,
        "redis_url": cfg.REDIS_URL,
        "max_super_admins": cfg.MAX_SUPER_ADMINS,
    }