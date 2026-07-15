# =+= NEW MODULE - Added 2026-07-15 by Codex =+=\n\n"""
异步影子 Worker - 后台任务处理器

功能：
  - 优先级任务队列（HIGH / MEDIUM / LOW）
  - 多 Worker 线程并行消费
  - 自动重试（可配置最大重试次数）
  - 任务状态追踪（pending / running / done / failed）
  - 优雅关闭
"""
import threading, queue, time, uuid
from enum import Enum
from typing import Callable, Optional
from datetime import datetime
from loguru import logger


class TaskPriority(Enum):
    LOW = 0
    MEDIUM = 1
    HIGH = 2


class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class ShadowTask:
    """单个后台任务"""

    def __init__(self, name: str, fn: Callable, priority: TaskPriority = TaskPriority.MEDIUM, max_retries: int = 0):
        self.id = str(uuid.uuid4())[:8]
        self.name = name
        self.fn = fn
        self.priority = priority
        self.max_retries = max_retries
        self.status = TaskStatus.PENDING
        self.retries = 0
        self.error: Optional[str] = None
        self.result = None
        self.created_at = datetime.now()
        self.started_at: Optional[datetime] = None
        self.finished_at: Optional[datetime] = None


class ShadowWorker:
    """影子 Worker - 无阻塞后台任务执行器"""

    def __init__(self, num_workers: int = 2):
        self._queue = queue.PriorityQueue()
        self._tasks: dict[str, ShadowTask] = {}
        self._lock = threading.Lock()
        self._running = True
        self._workers = []

        for i in range(num_workers):
            t = threading.Thread(target=self._worker_loop, daemon=True, name=f"ShadowWorker-{i}")
            t.start()
            self._workers.append(t)
            logger.info("ShadowWorker-{} started", i)

    def submit(self, task: ShadowTask) -> str:
        """提交任务，返回 task_id"""
        with self._lock:
            self._tasks[task.id] = task
        self._queue.put((task.priority.value, task.id))
        logger.debug("Task submitted: {} ({})", task.name, task.id)
        return task.id

    def get_status(self, task_id: str) -> Optional[ShadowTask]:
        """查询任务状态"""
        return self._tasks.get(task_id)

    def wait_all(self, timeout: Optional[float] = None):
        """等待所有任务完成"""
        deadline = time.time() + timeout if timeout else None
        while True:
            with self._lock:
                pending = [t for t in self._tasks.values() if t.status in (TaskStatus.PENDING, TaskStatus.RUNNING)]
                if not pending:
                    break
            if deadline and time.time() > deadline:
                break
            time.sleep(0.1)

    def shutdown(self, wait: bool = True):
        """关闭 Worker"""
        self._running = False
        if wait:
            for w in self._workers:
                w.join(timeout=5)
        logger.info("ShadowWorker shut down")

    def _worker_loop(self):
        while self._running:
            try:
                _, task_id = self._queue.get(timeout=1)
            except queue.Empty:
                continue

            with self._lock:
                task = self._tasks.get(task_id)
                if task is None:
                    continue
                task.status = TaskStatus.RUNNING
                task.started_at = datetime.now()

            try:
                task.result = task.fn()
                task.status = TaskStatus.DONE
                logger.debug("Task done: {} ({})", task.name, task.id)
            except Exception as e:
                task.error = str(e)
                task.retries += 1
                if task.retries <= task.max_retries:
                    task.status = TaskStatus.PENDING
                    self._queue.put((task.priority.value, task.id))
                    logger.warning("Task retry {}/{}: {} - {}", task.retries, task.max_retries, task.name, e)
                else:
                    task.status = TaskStatus.FAILED
                    logger.error("Task failed: {} - {}", task.name, e)
            finally:
                task.finished_at = datetime.now()


# 全局单例
_default_worker: Optional[ShadowWorker] = None


def get_worker() -> ShadowWorker:
    global _default_worker
    if _default_worker is None:
        _default_worker = ShadowWorker(num_workers=2)
    return _default_worker