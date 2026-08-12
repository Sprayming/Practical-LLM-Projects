"""
ab_testing.py —— A/B 实验管理 API 模块

【作用与功能】
本模块为 legal-doc-rag 提供 A/B 测试相关的 HTTP 接口，覆盖实验的 CRUD、变体分配、
行为事件上报与结果统计。通过管理员/用户两级权限依赖，将请求转发至底层 AB 管理器，
支撑前端灰度实验与回答质量对比。

【主要组成】
- `_require_admin`:管理员权限依赖，校验 Token 与 super_admin 角色。
- `create_experiment` / `list_experiments` / `get_experiment_results` / `start_experiment` / `stop_experiment` / `delete_experiment`:实验管理(CRUD 与启停)。
- `add_variant`:为实验添加变体(配置与权重)。
- `get_variant`:获取当前用户在实验中的分配变体。
- `record_event`:记录用户在实验中的行为事件。
- `CreateExperimentRequest` / `AddVariantRequest` / `RecordEventRequest`:请求数据模型。

【适用场景】
- 管理员在后台创建/启停实验、配置变体并查看统计结果。
- 前端用户在对话页面参与实验分流、上报行为事件以计算转化率。

【依赖关系】
- 上游调用方:管理后台前端、对话前端。
- 下游依赖:app.evaluation.ab_testing(get_ab_manager)、app.api.auth。
"""
import os
import sys

# 将项目根目录添加到系统路径中，以便正确导入项目内的其他模块
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel
from typing import Optional, Dict
from app.evaluation.ab_testing import get_ab_manager
from app.api.auth import get_user_from_token, require_user

# 创建 API 路由器实例，统一添加 /api/ab-testing 前缀，并打上 "ab-testing" 标签用于文档分类
router = APIRouter(prefix="/api/ab-testing", tags=["ab-testing"])


def _require_admin(authorization: str = Header(...)) -> dict:
    """
    依赖注入函数:校验请求是否具有管理员权限。
    
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


class CreateExperimentRequest(BaseModel):
    """
    创建实验请求的数据模型。
    
    属性:
        name (str): 实验名称。
        description (Optional[str]): 实验描述信息，可选。
        traffic_percent (int): 实验流量占比(0-100)，默认为 100% 表示所有用户参与。
    """
    name: str
    description: Optional[str] = None
    traffic_percent: int = 100


class AddVariantRequest(BaseModel):
    """
    添加实验变体请求的数据模型。
    
    属性:
        name (str): 变体名称(如:对照组 A、实验组 B)。
        weight (int): 变体流量权重，决定分配比例，默认为 1。
        config (Optional[Dict]): 变体配置参数，用于覆盖默认系统行为，可选。
    """
    name: str
    weight: int = 1
    config: Optional[Dict] = None


class RecordEventRequest(BaseModel):
    """
    记录实验事件请求的数据模型。
    
    属性:
        experiment_id (int): 关联的实验 ID。
        variant_id (int): 用户当前所处的变体 ID。
        event_type (str): 事件类型(如:点击、提交、回答点赞等)。
        event_data (Optional[Dict]): 事件附加数据，可选。
    """
    experiment_id: int
    variant_id: int
    event_type: str
    event_data: Optional[Dict] = None


# ============================================================
# Experiment Management (实验管理接口)
# ============================================================

@router.post("/experiments")
def create_experiment(req: CreateExperimentRequest, admin: dict = Depends(_require_admin)):
    """
    创建新的 A/B 测试实验。
    
    需要管理员权限。将实验配置传入管理器进行创建。
    
    参数:
        req (CreateExperimentRequest): 创建实验的请求数据。
        admin (dict): 依赖注入获取的管理员信息(自动完成权限校验)。
        
    异常:
        HTTPException: 如果创建失败(如名称重复等)，抛出 400 异常。
        
    返回:
        dict: 包含成功标志、消息和新创建的 experiment_id。
    """
    manager = get_ab_manager()
    ok, msg, experiment_id = manager.create_experiment(req.name, req.description, req.traffic_percent)
    if not ok:
        raise HTTPException(400, msg)
    return {"success": True, "message": msg, "experiment_id": experiment_id}


@router.get("/experiments")
def list_experiments(admin: dict = Depends(_require_admin)):
    """
    获取所有实验列表。
    
    需要管理员权限。返回系统中已创建的所有 A/B 测试实验。
    
    参数:
        admin (dict): 依赖注入获取的管理员信息。
        
    返回:
        dict: 包含实验列表 experiments 和总数 total。
    """
    manager = get_ab_manager()
    experiments = manager.list_experiments()
    return {"experiments": experiments, "total": len(experiments)}


@router.get("/experiments/{experiment_id}")
def get_experiment_results(experiment_id: int, admin: dict = Depends(_require_admin)):
    """
    获取指定实验的统计结果。
    
    需要管理员权限。返回该实验下各变体的流量、事件转化等聚合数据。
    
    参数:
        experiment_id (int): 要查询的实验 ID。
        admin (dict): 依赖注入获取的管理员信息。
        
    返回:
        dict: 实验结果统计数据。
    """
    manager = get_ab_manager()
    results = manager.get_experiment_results(experiment_id)
    return results


@router.put("/experiments/{experiment_id}/start")
def start_experiment(experiment_id: int, admin: dict = Depends(_require_admin)):
    """
    启动指定实验，开始分配流量。
    
    需要管理员权限。将实验状态从暂停/草稿变更为运行中。
    
    参数:
        experiment_id (int): 要启动的实验 ID。
        admin (dict): 依赖注入获取的管理员信息。
        
    异常:
        HTTPException: 如果启动失败(如状态不合法)，抛出 400 异常。
        
    返回:
        dict: 包含成功标志和消息。
    """
    manager = get_ab_manager()
    ok, msg = manager.start_experiment(experiment_id)
    if not ok:
        raise HTTPException(400, msg)
    return {"success": True, "message": msg}


@router.put("/experiments/{experiment_id}/stop")
def stop_experiment(experiment_id: int, admin: dict = Depends(_require_admin)):
    """
    停止指定实验，停止分配流量。
    
    需要管理员权限。将实验状态变更为已停止。
    
    参数:
        experiment_id (int): 要停止的实验 ID。
        admin (dict): 依赖注入获取的管理员信息。
        
    异常:
        HTTPException: 如果停止失败，抛出 400 异常。
        
    返回:
        dict: 包含成功标志和消息。
    """
    manager = get_ab_manager()
    ok, msg = manager.stop_experiment(experiment_id)
    if not ok:
        raise HTTPException(400, msg)
    return {"success": True, "message": msg}


@router.delete("/experiments/{experiment_id}")
def delete_experiment(experiment_id: int, admin: dict = Depends(_require_admin)):
    """
    删除指定实验及其关联数据。
    
    需要管理员权限。谨慎操作，删除后不可恢复。
    
    参数:
        experiment_id (int): 要删除的实验 ID。
        admin (dict): 依赖注入获取的管理员信息。
        
    异常:
        HTTPException: 如果删除失败，抛出 400 异常。
        
    返回:
        dict: 包含成功标志和消息。
    """
    manager = get_ab_manager()
    ok, msg = manager.delete_experiment(experiment_id)
    if not ok:
        raise HTTPException(400, msg)
    return {"success": True, "message": msg}


# ============================================================
# Variant Management (变体管理接口)
# ============================================================

@router.post("/experiments/{experiment_id}/variants")
def add_variant(experiment_id: int, req: AddVariantRequest, admin: dict = Depends(_require_admin)):
    """
    为指定实验添加新的变体。
    
    需要管理员权限。例如为实验添加对照组或不同的实验组配置。
    
    参数:
        experiment_id (int): 目标实验 ID。
        req (AddVariantRequest): 添加变体的请求数据。
        admin (dict): 依赖注入获取的管理员信息。
        
    异常:
        HTTPException: 如果添加失败，抛出 400 异常。
        
    返回:
        dict: 包含成功标志、消息和新创建的 variant_id。
    """
    manager = get_ab_manager()
    ok, msg, variant_id = manager.add_variant(experiment_id, req.name, req.weight, req.config)
    if not ok:
        raise HTTPException(400, msg)
    return {"success": True, "message": msg, "variant_id": variant_id}


# ============================================================
# User Assignment (用户分配接口)
# ============================================================

@router.get("/variant/{experiment_id}")
def get_variant(experiment_id: int, user: dict = Depends(require_user)):
    """
    获取当前用户在指定实验中分配到的变体。
    
    普通用户权限即可访问。如果用户尚未分配，系统会根据权重自动分配并返回。
    
    参数:
        experiment_id (int): 要查询的实验 ID。
        user (dict): 依赖注入获取的当前登录用户信息。
        
    返回:
        dict: 包含分配给该用户的变体信息 variant。
    """
    manager = get_ab_manager()
    user_id = str(user.get("id", ""))
    variant = manager.get_variant_for_user(experiment_id, user_id)
    return {"variant": variant}


# ============================================================
# Event Recording (事件记录接口)
# ============================================================

@router.post("/events")
def record_event(req: RecordEventRequest, user: dict = Depends(require_user)):
    """
    记录当前用户在实验中触发的行为事件。
    
    普通用户权限即可访问。前端在用户触发特定行为(如点赞、提交)时调用此接口上报数据，
    用于后续计算实验转化率。
    
    参数:
        req (RecordEventRequest): 包含实验ID、变体ID、事件类型等信息的请求数据。
        user (dict): 依赖注入获取的当前登录用户信息。
        
    异常:
        HTTPException: 如果记录失败(如数据库异常)，抛出 500 异常。
        
    返回:
        dict: 包含成功标志。
    """
    manager = get_ab_manager()
    user_id = str(user.get("id", ""))
    success = manager.record_event(
        req.experiment_id,
        req.variant_id,
        req.event_type,
        user_id,
        req.event_data,
    )
    if not success:
        raise HTTPException(500, "Failed to record event")
    return {"success": True}
