"""
category.py —— 文档分类管理 API 模块

【作用与功能】
本模块为 legal-doc-rag 提供文档分类的 HTTP 接口，支持分类的 CRUD、将文档归类到指定
分类以及按分类检索文档列表。所有操作按 tenant_id 隔离，是组织与检索租户内法律文档的
基础管理能力。

【主要组成】
- `create` / `list_all` / `delete`：分类的创建、列举与删除。
- `assign_document`：为指定文档设置/取消分类。
- `get_document_category_info`：查询某文档所属分类。
- `list_documents`：按分类（可选）列出文档。
- `CreateCategoryRequest` / `SetDocumentCategoryRequest`：请求数据模型。

【适用场景】
- 用户在知识库管理页创建分类并对文档做归类，便于后续按分类浏览与检索。

【依赖关系】
- 上游调用方：知识库/文档管理前端。
- 下游依赖：app.tenant.category、app.api.auth。
"""
import os
import sys

# 将项目根目录添加到系统路径中，以便正确导入项目内的其他模块
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
# 导入租户分类管理的底层操作函数
from app.tenant.category import (
    create_category,
    list_categories,
    delete_category,
    set_document_category,
    get_document_category,
    list_documents_by_category,
)
from app.api.auth import get_user_from_token, require_user

# 创建 API 路由器实例，统一添加 /api/categories 前缀，并打上 "categories" 标签用于文档分类
router = APIRouter(prefix="/api/categories", tags=["categories"])


class CreateCategoryRequest(BaseModel):
    """
    创建分类请求的数据模型。
    
    属性：
        name (str): 分类名称。
        description (Optional[str]): 分类描述信息，可选。
    """
    name: str
    description: Optional[str] = None


class SetDocumentCategoryRequest(BaseModel):
    """
    设置文档分类请求的数据模型。
    
    属性：
        filename (str): 目标文档的文件名。
        category_id (Optional[int]): 要分配到的分类 ID。如果为 None，表示取消该文档的分类关联。
    """
    filename: str
    category_id: Optional[int] = None


# ============================================================
# Category Management (分类管理接口)
# ============================================================

@router.post("")
def create(req: CreateCategoryRequest, user: dict = Depends(require_user)):
    """
    创建新的文档分类。
    
    需要用户登录。在同一租户下创建新的分类。
    
    参数：
        req (CreateCategoryRequest): 包含分类名称和描述的请求体。
        user (dict): 依赖注入获取的当前登录用户信息，用于提取 tenant_id。
        
    异常：
        HTTPException: 如果创建失败（如分类名称重复），抛出 400 异常。
        
    返回：
        dict: 包含成功标志和操作消息。
    """
    tenant_id = user["tenant_id"]
    ok, msg = create_category(tenant_id, req.name, req.description)
    if not ok:
        raise HTTPException(400, msg)
    return {"success": True, "message": msg}


@router.get("")
def list_all(user: dict = Depends(require_user)):
    """
    获取当前租户下的所有文档分类列表。
    
    需要用户登录。返回该租户拥有的所有分类信息。
    
    参数：
        user (dict): 依赖注入获取的当前登录用户信息，用于提取 tenant_id。
        
    返回：
        dict: 包含分类列表 categories 和总数 total。
    """
    tenant_id = user["tenant_id"]
    categories = list_categories(tenant_id)
    return {"categories": categories, "total": len(categories)}


@router.delete("/{category_id}")
def delete(category_id: int, user: dict = Depends(require_user)):
    """
    删除指定的文档分类。
    
    需要用户登录。根据分类 ID 删除指定分类。
    
    参数：
        category_id (int): 路径参数，待删除的分类 ID。
        user (dict): 依赖注入获取的当前登录用户信息，用于提取 tenant_id。
        
    异常：
        HTTPException: 如果删除失败（如分类不存在或存在关联文档），抛出 400 异常。
        
    返回：
        dict: 包含成功标志和操作消息。
    """
    tenant_id = user["tenant_id"]
    ok, msg = delete_category(tenant_id, category_id)
    if not ok:
        raise HTTPException(400, msg)
    return {"success": True, "message": msg}


# ============================================================
# Document Classification (文档归类接口)
# ============================================================

@router.post("/assign")
def assign_document(req: SetDocumentCategoryRequest, user: dict = Depends(require_user)):
    """
    为指定文档设置或更新分类。
    
    需要用户登录。将指定的文档分配到某个分类下，如果 category_id 为空则取消其分类。
    
    参数：
        req (SetDocumentCategoryRequest): 包含文档名和目标分类 ID 的请求体。
        user (dict): 依赖注入获取的当前登录用户信息，用于提取 tenant_id。
        
    异常：
        HTTPException: 如果分配失败（如文档或分类不存在），抛出 400 异常。
        
    返回：
        dict: 包含成功标志和操作消息。
    """
    tenant_id = user["tenant_id"]
    ok, msg = set_document_category(tenant_id, req.filename, req.category_id)
    if not ok:
        raise HTTPException(400, msg)
    return {"success": True, "message": msg}


@router.get("/document/{filename}")
def get_document_category_info(filename: str, user: dict = Depends(require_user)):
    """
    获取指定文档所属的分类信息。
    
    需要用户登录。根据文档名查询其当前关联的分类详情。
    
    参数：
        filename (str): 路径参数，目标文档的文件名。
        user (dict): 依赖注入获取的当前登录用户信息，用于提取 tenant_id。
        
    返回：
        dict: 包含该文档的分类信息 category。如果未分类，则可能返回 None。
    """
    tenant_id = user["tenant_id"]
    category = get_document_category(tenant_id, filename)
    return {"category": category}


@router.get("/list")
def list_documents(category_id: Optional[int] = None, user: dict = Depends(require_user)):
    """
    获取文档列表，支持按分类进行筛选。
    
    需要用户登录。如果不传 category_id，则返回该租户下的所有文档；如果传入，则只返回指定分类下的文档。
    
    参数：
        category_id (Optional[int]): 查询参数，可选的分类 ID，用于过滤文档。
        user (dict): 依赖注入获取的当前登录用户信息，用于提取 tenant_id。
        
    返回：
        dict: 包含文档列表 documents 和总数 total。
    """
    tenant_id = user["tenant_id"]
    documents = list_documents_by_category(tenant_id, category_id)
    return {"documents": documents, "total": len(documents)}
