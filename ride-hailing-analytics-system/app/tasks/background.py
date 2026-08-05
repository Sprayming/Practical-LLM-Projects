import asyncio
import uuid
from typing import Optional, Callable, Any
from datetime import datetime
from loguru import logger
from enum import Enum


class TaskStatus(str, Enum):
    """任务状态枚举"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class BackgroundTask:
    """后台任务"""
    
    def __init__(self, task_id: str, func: Callable, args: tuple = (), kwargs: dict = None):
        self.task_id = task_id
        self.func = func
        self.args = args
        self.kwargs = kwargs or {}
        self.status = TaskStatus.PENDING
        self.result = None
        self.error = None
        self.created_at = datetime.now()
        self.started_at = None
        self.completed_at = None
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "task_id": self.task_id,
            "status": self.status.value,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None
        }


class TaskManager:
    """任务管理器"""
    
    def __init__(self):
        self.tasks = {}
        self._running = False
    
    def submit(self, func: Callable, *args, **kwargs) -> str:
        """
        提交异步任务
        
        Args:
            func: 要执行的函数
            *args: 位置参数
            **kwargs: 关键字参数
        
        Returns:
            任务ID
        """
        task_id = str(uuid.uuid4())[:8]
        task = BackgroundTask(task_id, func, args, kwargs)
        self.tasks[task_id] = task
        
        # 在后台执行任务
        asyncio.create_task(self._run_task(task))
        
        logger.info("任务已提交: {}", task_id)
        return task_id
    
    async def _run_task(self, task: BackgroundTask):
        """执行任务"""
        task.status = TaskStatus.RUNNING
        task.started_at = datetime.now()
        
        try:
            if asyncio.iscoroutinefunction(task.func):
                task.result = await task.func(*task.args, **task.kwargs)
            else:
                task.result = task.func(*task.args, **task.kwargs)
            
            task.status = TaskStatus.COMPLETED
            logger.info("任务完成: {}", task.task_id)
        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error = str(e)
            logger.error("任务失败: {} - {}", task.task_id, e)
        finally:
            task.completed_at = datetime.now()
    
    def get_task(self, task_id: str) -> Optional[dict]:
        """获取任务状态"""
        task = self.tasks.get(task_id)
        return task.to_dict() if task else None
    
    def list_tasks(self, status: Optional[TaskStatus] = None) -> list:
        """列出任务"""
        tasks = list(self.tasks.values())
        if status:
            tasks = [t for t in tasks if t.status == status]
        return [t.to_dict() for t in tasks]
    
    def cleanup(self, max_age_hours: int = 24):
        """清理过期任务"""
        now = datetime.now()
        to_delete = []
        
        for task_id, task in self.tasks.items():
            if task.completed_at:
                age = (now - task.completed_at).total_seconds() / 3600
                if age > max_age_hours:
                    to_delete.append(task_id)
        
        for task_id in to_delete:
            del self.tasks[task_id]
        
        if to_delete:
            logger.info("清理了 {} 个过期任务", len(to_delete))


# 全局任务管理器实例
task_manager = TaskManager()


# 示例异步任务
async def long_running_query(question: str) -> dict:
    """长时间运行的查询任务"""
    # 模拟长时间查询
    await asyncio.sleep(2)
    return {
        "question": question,
        "status": "completed",
        "result": "查询结果"
    }


async def data_export_task(format: str, query_ids: list) -> str:
    """数据导出任务"""
    # 模拟导出
    await asyncio.sleep(1)
    return f"export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{format}"


async def cache_warmup_task():
    """缓存预热任务"""
    # 模拟缓存预热
    await asyncio.sleep(1)
    return {"warmed_up": True}