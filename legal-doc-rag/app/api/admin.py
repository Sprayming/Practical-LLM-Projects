"""
admin.py —— 系统管理与运营 API 模块

【作用与功能】
本模块为 legal-doc-rag 提供超级管理员专属的后台管理接口，包含用户管理、系统统计
与运行配置查看三大职责。所有接口均通过 `_require_admin` 依赖强制校验 super_admin 角色，
是平台运营与运维的核心入口。

【主要组成】
- `_require_admin`：超级管理员权限依赖，校验 Token 与 super_admin 角色。
- `list_users`：查询全量用户列表。
- `update_user_role`：调整用户角色（含名额上限与防自杀校验）。
- `delete_user`：删除指定用户（禁止删除自身）。
- `get_stats`：聚合用户/文档/向量数与系统指标、链路追踪。
- `get_config`：读取当前核心运行配置。
- `DeleteUserRequest` / `SetRoleRequest`：请求数据模型。

【适用场景】
- 超级管理员在后台管理用户、监控文档/向量规模与系统运行指标。
- 运维排查问题时查看运行配置与链路追踪摘要。

【依赖关系】
- 上游调用方：管理后台前端。
- 下游依赖：app.tenant.auth、app.core.config、app.observability.monitoring、
  app.observability.tracker、Chroma 向量库。
"""
import os
import sys

# 将项目根目录添加到系统路径中，以便正确导入项目内的其他模块
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel
from typing import Optional
import app.core.config as cfg
from app.api.auth import get_user_from_token
from app.tenant.auth import has_users, list_users as list_users_db, delete_user, set_user_role as set_user_role_db

# 创建 API 路由器实例，统一添加 /api/admin 前缀，并打上 "admin" 标签用于文档分类
router = APIRouter(prefix="/api/admin", tags=["admin"])


def _require_admin(authorization: str = Header(...)) -> dict:
    """
    依赖注入函数：校验请求是否具有超级管理员权限。
    
    从请求头提取 Authorization Token，验证用户身份，并检查其角色是否为 super_admin。
    如果不是管理员或 Token 无效，则抛出 HTTP 异常阻断请求。
    
    参数：
        authorization (str): 请求头中的 Authorization 字段值，预期格式为 "Bearer <token>"。
        
    异常：
        HTTPException: 如果缺少 Token 抛出 401 异常；如果用户不是超级管理员抛出 403 异常。
        
    返回：
        dict: 验证通过后的当前用户信息字典。
    """
    # 去除 "Bearer " 前缀，提取纯 Token 字符串
    token = authorization.replace("Bearer ", "").strip()
    if not token:
        raise HTTPException(401, "Missing token")
    user = get_user_from_token(token)
    # 权限校验：仅允许 super_admin 角色访问
    if user.get("role") != "super_admin":
        raise HTTPException(403, "Admin access required")
    return user


# ============================================================
# User Management (用户管理接口)
# ============================================================

@router.get("/users")
def list_users(admin: dict = Depends(_require_admin)):
    """
    获取系统中所有用户的列表。
    
    需要超级管理员权限。返回所有注册用户的详细信息及总数。
    
    参数：
        admin (dict): 依赖注入获取的管理员信息（自动完成权限校验）。
        
    返回：
        dict: 包含用户列表 users 和总数 total。
    """
    users = list_users_db()
    return {"users": users, "total": len(users)}


class DeleteUserRequest(BaseModel):
    """
    删除用户请求的数据模型（预留，当前接口使用路径参数）。
    """
    username: str


class SetRoleRequest(BaseModel):
    """
    设置用户角色请求的数据模型。
    
    属性：
        role (str): 目标角色，仅支持 "super_admin" (超级管理员) 或 "user" (普通用户)。
    """
    role: str  # "super_admin" | "user"


@router.put("/users/{username}/role")
def update_user_role(
    username: str, req: SetRoleRequest, admin: dict = Depends(_require_admin)
):
    """
    手动设置用户角色：提权为超级管理员 / 降级为普通用户。
    
    业务规则：
    - 不允许修改自己的角色（避免误操作锁死权限）。
    - 提权为超级管理员时受 cfg.MAX_SUPER_ADMINS 名额上限限制。
    
    参数：
        username (str): 路径参数，待修改角色的用户名。
        req (SetRoleRequest): 包含目标角色的请求数据。
        admin (dict): 依赖注入获取的当前管理员信息。
        
    异常：
        HTTPException: 如果修改自己角色抛出 400；角色无效抛出 400；名额已满抛出 403；用户不存在抛出 404。
        
    返回：
        dict: 包含成功标志和操作消息。
    """
    # 安全校验：禁止修改自身角色
    if username == admin.get("username"):
        raise HTTPException(400, "不能修改自己的角色")
    # 参数校验：角色必须是预设值之一
    if req.role not in ("super_admin", "user"):
        raise HTTPException(400, "无效的角色")

    # 名额校验：提权为超级管理员时检查系统上限
    if req.role == "super_admin":
        users = list_users_db()
        current = sum(1 for u in users if u.get("role") == "super_admin")
        if current >= cfg.MAX_SUPER_ADMINS:
            raise HTTPException(
                403, f"超级管理员名额已满（最多 {cfg.MAX_SUPER_ADMINS} 个）"
            )

    # 执行数据库更新操作
    ok, msg = set_user_role_db(username, req.role)
    if not ok:
        # 根据返回消息判断是用户不存在还是其他错误
        raise HTTPException(404 if "不存在" in msg else 400, msg)
    return {"success": True, "message": msg}


@router.delete("/users/{username}")
def delete_user(username: str, admin: dict = Depends(_require_admin)):
    """
    删除指定用户。
    
    需要超级管理员权限。为了系统安全，不允许管理员删除自己的账号。
    
    参数：
        username (str): 路径参数，待删除的用户名。
        admin (dict): 依赖注入获取的当前管理员信息。
        
    异常：
        HTTPException: 如果尝试删除自己抛出 400；用户不存在抛出 404。
        
    返回：
        dict: 包含成功标志和确认消息。
    """
    # 安全校验：禁止删除自身账号
    if username == admin.get("username"):
        raise HTTPException(400, "Cannot delete yourself")

    ok = delete_user(username)
    if not ok:
        raise HTTPException(404, "User not found")

    return {"success": True, "message": f"User '{username}' deleted"}


# ============================================================
# System Statistics (系统统计接口)
# ============================================================

@router.get("/stats")
def get_stats(admin: dict = Depends(_require_admin)):
    """
    获取系统运行统计数据。
    
    需要超级管理员权限。聚合返回用户统计、文档统计、向量库统计以及系统监控指标。
    
    参数：
        admin (dict): 依赖注入获取的当前管理员信息。
        
    返回：
        dict: 包含各维度统计数据的字典：
              - users: 用户总数及管理员数。
              - documents: 文档总数。
              - vectors: 向量总数。
              - metrics: 系统运行指标。
              - traces: 链路追踪摘要。
    """
    # 延迟导入监控和追踪模块，避免循环依赖
    from app.observability.monitoring import get_metrics_collector
    from app.observability.tracker import get_trace_store

    collector = get_metrics_collector()
    trace_store = get_trace_store()

    # 1. 统计用户数据
    users = list_users_db()
    user_count = len(users)
    admin_count = sum(1 for u in users if u.get("role") == "super_admin")

    # 2. 统计文档数据：遍历上传目录统计 PDF 文件数量
    import os
    doc_count = 0
    upload_dir = cfg.UPLOAD_DIR
    if os.path.exists(upload_dir):
        for tenant_dir in os.listdir(upload_dir):
            tenant_path = os.path.join(upload_dir, tenant_dir)
            if os.path.isdir(tenant_path):
                doc_count += len([f for f in os.listdir(tenant_path) if f.endswith(".pdf")])

    # 3. 统计向量数据：遍历 Chroma 持久化目录，汇总各租户集合中的向量数
    vector_count = 0
    chroma_dir = cfg.CHROMA_PERSIST_DIR
    if os.path.exists(chroma_dir):
        for tenant_dir in os.listdir(chroma_dir):
            tenant_path = os.path.join(chroma_dir, tenant_dir)
            if os.path.isdir(tenant_path):
                try:
                    import chromadb
                    # 使用持久化客户端连接本地向量库
                    client = chromadb.PersistentClient(path=tenant_path)
                    # 累加该租户下所有 Collection 的记录数
                    for col in client.list_collections():
                        vector_count += col.count()
                except Exception:
                    # 某个租户目录读取异常时跳过，不影响整体接口响应
                    pass

    # 4. 获取系统运行时指标和追踪摘要
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
# Configuration (配置管理接口)
# ============================================================

@router.get("/config")
def get_config(admin: dict = Depends(_require_admin)):
    """
    获取当前系统的核心运行配置。
    
    需要超级管理员权限。用于后台管理界面展示当前生效的模型、存储路径等配置信息。
    
    参数：
        admin (dict): 依赖注入获取的当前管理员信息。
        
    返回：
        dict: 包含各项核心配置项的字典。
    """
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
