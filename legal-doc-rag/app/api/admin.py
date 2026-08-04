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
from app.api.auth import get_user_from_token, _tokens
from app.tenant.auth import has_users, _load_users, _save_users

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
    users = _load_users()
    user_list = []
    for uid, user_data in users.items():
        user_list.append({
            "user_id": uid,
            "username": user_data.get("username", ""),
            "tenant_id": user_data.get("tenant_id", ""),
            "role": user_data.get("role", "user"),
            "created_at": user_data.get("created_at", ""),
        })
    return {"users": user_list, "total": len(user_list)}


class DeleteUserRequest(BaseModel):
    username: str


@router.delete("/users/{username}")
def delete_user(username: str, admin: dict = Depends(_require_admin)):
    """Delete a user (admin only)."""
    users = _load_users()

    # Find user by username
    target_uid = None
    for uid, user_data in users.items():
        if user_data.get("username") == username:
            target_uid = uid
            break

    if not target_uid:
        raise HTTPException(404, "User not found")

    # Prevent deleting yourself
    if users[target_uid].get("username") == admin.get("username"):
        raise HTTPException(400, "Cannot delete yourself")

    # Delete user
    del users[target_uid]
    _save_users(users)

    # Remove token if exists
    tokens_to_remove = [t for t, u in _tokens.items() if u.get("username") == username]
    for t in tokens_to_remove:
        _tokens.pop(t, None)

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
    users = _load_users()
    user_count = len(users)
    admin_count = sum(1 for u in users.values() if u.get("role") == "super_admin")

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
    }