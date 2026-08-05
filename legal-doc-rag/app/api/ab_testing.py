"""
A/B Testing API for Legal-DOC-RAG.

Provides endpoints for:
- Experiment management (CRUD)
- Variant assignment
- Event recording
- Results viewing
"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel
from typing import Optional, Dict
from app.evaluation.ab_testing import get_ab_manager
from app.api.auth import get_user_from_token, require_user

router = APIRouter(prefix="/api/ab-testing", tags=["ab-testing"])


def _require_admin(authorization: str = Header(...)) -> dict:
    """Require admin role for access."""
    token = authorization.replace("Bearer ", "").strip()
    if not token:
        raise HTTPException(401, "Missing token")
    user = get_user_from_token(token)
    if user.get("role") != "super_admin":
        raise HTTPException(403, "Admin access required")
    return user



class CreateExperimentRequest(BaseModel):
    name: str
    description: Optional[str] = None
    traffic_percent: int = 100


class AddVariantRequest(BaseModel):
    name: str
    weight: int = 1
    config: Optional[Dict] = None


class RecordEventRequest(BaseModel):
    experiment_id: int
    variant_id: int
    event_type: str
    event_data: Optional[Dict] = None


# ============================================================
# Experiment Management
# ============================================================

@router.post("/experiments")
def create_experiment(req: CreateExperimentRequest, admin: dict = Depends(_require_admin)):
    """创建新实验"""
    manager = get_ab_manager()
    ok, msg, experiment_id = manager.create_experiment(req.name, req.description, req.traffic_percent)
    if not ok:
        raise HTTPException(400, msg)
    return {"success": True, "message": msg, "experiment_id": experiment_id}


@router.get("/experiments")
def list_experiments(admin: dict = Depends(_require_admin)):
    """列出所有实验"""
    manager = get_ab_manager()
    experiments = manager.list_experiments()
    return {"experiments": experiments, "total": len(experiments)}


@router.get("/experiments/{experiment_id}")
def get_experiment_results(experiment_id: int, admin: dict = Depends(_require_admin)):
    """获取实验结果"""
    manager = get_ab_manager()
    results = manager.get_experiment_results(experiment_id)
    return results


@router.put("/experiments/{experiment_id}/start")
def start_experiment(experiment_id: int, admin: dict = Depends(_require_admin)):
    """启动实验"""
    manager = get_ab_manager()
    ok, msg = manager.start_experiment(experiment_id)
    if not ok:
        raise HTTPException(400, msg)
    return {"success": True, "message": msg}


@router.put("/experiments/{experiment_id}/stop")
def stop_experiment(experiment_id: int, admin: dict = Depends(_require_admin)):
    """停止实验"""
    manager = get_ab_manager()
    ok, msg = manager.stop_experiment(experiment_id)
    if not ok:
        raise HTTPException(400, msg)
    return {"success": True, "message": msg}


@router.delete("/experiments/{experiment_id}")
def delete_experiment(experiment_id: int, admin: dict = Depends(_require_admin)):
    """删除实验"""
    manager = get_ab_manager()
    ok, msg = manager.delete_experiment(experiment_id)
    if not ok:
        raise HTTPException(400, msg)
    return {"success": True, "message": msg}


# ============================================================
# Variant Management
# ============================================================

@router.post("/experiments/{experiment_id}/variants")
def add_variant(experiment_id: int, req: AddVariantRequest, admin: dict = Depends(_require_admin)):
    """添加实验变体"""
    manager = get_ab_manager()
    ok, msg, variant_id = manager.add_variant(experiment_id, req.name, req.weight, req.config)
    if not ok:
        raise HTTPException(400, msg)
    return {"success": True, "message": msg, "variant_id": variant_id}


# ============================================================
# User Assignment
# ============================================================

@router.get("/variant/{experiment_id}")
def get_variant(experiment_id: int, user: dict = Depends(require_user)):
    """获取用户当前变体"""
    manager = get_ab_manager()
    user_id = str(user.get("id", ""))
    variant = manager.get_variant_for_user(experiment_id, user_id)
    return {"variant": variant}


# ============================================================
# Event Recording
# ============================================================

@router.post("/events")
def record_event(req: RecordEventRequest, user: dict = Depends(require_user)):
    """记录实验事件"""
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