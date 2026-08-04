"""
Category API for Legal-DOC-RAG.

Provides endpoints for:
- Category management (CRUD)
- Document classification
- Category-based document listing
"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel
from typing import Optional
from app.tenant.category import (
    create_category,
    list_categories,
    delete_category,
    set_document_category,
    get_document_category,
    list_documents_by_category,
)
from app.api.auth import get_user_from_token

router = APIRouter(prefix="/api/categories", tags=["categories"])


def _require_user(authorization: str = Header(...)) -> dict:
    """Require authenticated user."""
    token = authorization.replace("Bearer ", "").strip()
    if not token:
        raise HTTPException(401, "Missing token")
    return get_user_from_token(token)


class CreateCategoryRequest(BaseModel):
    name: str
    description: Optional[str] = None


class SetDocumentCategoryRequest(BaseModel):
    filename: str
    category_id: Optional[int] = None


# ============================================================
# Category Management
# ============================================================

@router.post("")
def create(req: CreateCategoryRequest, user: dict = Depends(_require_user)):
    """创建文档分类"""
    tenant_id = user["tenant_id"]
    ok, msg = create_category(tenant_id, req.name, req.description)
    if not ok:
        raise HTTPException(400, msg)
    return {"success": True, "message": msg}


@router.get("")
def list_all(user: dict = Depends(_require_user)):
    """列出所有分类"""
    tenant_id = user["tenant_id"]
    categories = list_categories(tenant_id)
    return {"categories": categories, "total": len(categories)}


@router.delete("/{category_id}")
def delete(category_id: int, user: dict = Depends(_require_user)):
    """删除分类"""
    tenant_id = user["tenant_id"]
    ok, msg = delete_category(tenant_id, category_id)
    if not ok:
        raise HTTPException(400, msg)
    return {"success": True, "message": msg}


# ============================================================
# Document Classification
# ============================================================

@router.post("/assign")
def assign_document(req: SetDocumentCategoryRequest, user: dict = Depends(_require_user)):
    """设置文档分类"""
    tenant_id = user["tenant_id"]
    ok, msg = set_document_category(tenant_id, req.filename, req.category_id)
    if not ok:
        raise HTTPException(400, msg)
    return {"success": True, "message": msg}


@router.get("/document/{filename}")
def get_document_category_info(filename: str, user: dict = Depends(_require_user)):
    """获取文档的分类信息"""
    tenant_id = user["tenant_id"]
    category = get_document_category(tenant_id, filename)
    return {"category": category}


@router.get("/list")
def list_documents(category_id: Optional[int] = None, user: dict = Depends(_require_user)):
    """列出文档（可按分类筛选）"""
    tenant_id = user["tenant_id"]
    documents = list_documents_by_category(tenant_id, category_id)
    return {"documents": documents, "total": len(documents)}