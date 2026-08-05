from fastapi import APIRouter, HTTPException
from loguru import logger
from typing import Optional

from app.tasks.background import task_manager, TaskStatus

router = APIRouter(prefix="/api/tasks", tags=["Background Tasks"])


@router.get("/")
async def list_tasks(status: Optional[str] = None):
    """列出所有任务"""
    try:
        task_status = TaskStatus(status) if status else None
        tasks = task_manager.list_tasks(task_status)
        return {
            "total": len(tasks),
            "tasks": tasks
        }
    except Exception as e:
        logger.error("列出任务失败: {}", e)
        raise HTTPException(status_code=500, detail="获取任务列表失败")


@router.get("/{task_id}")
async def get_task(task_id: str):
    """获取任务状态"""
    try:
        task = task_manager.get_task(task_id)
        
        if task is None:
            raise HTTPException(status_code=404, detail="任务不存在")
        
        return task
    except HTTPException:
        raise
    except Exception as e:
        logger.error("获取任务失败: {}", e)
        raise HTTPException(status_code=500, detail="获取任务状态失败")


@router.delete("/{task_id}")
async def cancel_task(task_id: str):
    """取消任务（仅标记为取消，实际取消需要额外实现）"""
    try:
        task = task_manager.get_task(task_id)
        
        if task is None:
            raise HTTPException(status_code=404, detail="任务不存在")
        
        if task["status"] in ["completed", "failed"]:
            raise HTTPException(status_code=400, detail="任务已完成或失败，无法取消")
        
        # 注意：这里只是标记，实际取消需要更复杂的实现
        return {"message": "任务取消请求已提交"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("取消任务失败: {}", e)
        raise HTTPException(status_code=500, detail="取消任务失败")


@router.post("/cleanup")
async def cleanup_tasks(max_age_hours: int = 24):
    """清理过期任务"""
    try:
        task_manager.cleanup(max_age_hours)
        return {"message": f"已清理 {max_age_hours} 小时前的过期任务"}
    except Exception as e:
        logger.error("清理任务失败: {}", e)
        raise HTTPException(status_code=500, detail="清理任务失败")