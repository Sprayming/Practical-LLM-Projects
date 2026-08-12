"""
shadow_worker.py —— Legal-DOC-RAG 影子后台任务执行器

【作用与功能】
本模块实现一个轻量、无阻塞的后台任务执行框架「影子 Worker」:基于优先级
队列(HIGH/MEDIUM/LOW)与多个守护线程并行消费任务，支持可配置的最大重试
次数与任务状态追踪(pending/running/done/failed)，并提供优雅关闭能力。
业务可把耗时或可延迟的工作封装为 `ShadowTask` 提交，使请求线程不被阻塞。

【主要组成】
- `TaskPriority` / `TaskStatus`:任务优先级与状态枚举
- `ShadowTask`:单个后台任务的封装(含重试次数、状态、时间戳)
- `ShadowWorker`:优先级队列 + 多线程消费的执行器
- `get_worker()`:获取全局单例 Worker

【适用场景】
- 场景1:应用启动时 `get_worker()` 创建并常驻后台线程池
- 场景2:将可延迟任务(如统计、通知、清理)提交而不阻塞请求

【依赖关系】
- 上游调用方:应用启动流程、业务任务提交点
- 下游依赖:标准库 threading/queue、loguru
"""
#
# 功能:
#   - 优先级任务队列(HIGH / MEDIUM / LOW)
#   - 多 Worker 线程并行消费
#   - 自动重试(可配置最大重试次数)
#   - 任务状态追踪(pending / running / done / failed)
#   - 优雅关闭
import threading, queue, time, uuid
from enum import Enum
from typing import Callable, Optional
from datetime import datetime
from loguru import logger


class TaskPriority(Enum):
    """任务优先级枚举。

    数值越大优先级越高；放入优先队列时以 `value` 做比较，HIGH 会先于
    MEDIUM/LOW 被消费。
    """
    LOW = 0
    MEDIUM = 1
    HIGH = 2


class TaskStatus(Enum):
    """任务生命周期状态枚举。"""
    PENDING = "pending"   # 已提交、等待执行
    RUNNING = "running"   # 正在执行
    DONE = "done"         # 执行成功
    FAILED = "failed"     # 重试耗尽后仍失败


class ShadowTask:
    """单个后台任务的封装。

    持有任务的函数 `fn`、优先级、重试配置与运行时状态(状态、已重试次数、
    错误信息、结果及各类时间戳)，便于调用方追踪与查询。
    """

    def __init__(self, name: str, fn: Callable, priority: TaskPriority = TaskPriority.MEDIUM, max_retries: int = 0):
        """初始化一个后台任务。

        参数:
            name (str): 任务名称(用于日志展示)
            fn (Callable): 实际执行的可调用对象(无参)
            priority (TaskPriority): 优先级，默认 MEDIUM
            max_retries (int): 失败最大重试次数，默认 0(不重试)
        """
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
    """影子 Worker —— 无阻塞后台任务执行器。

    内部维护一个优先级队列与一组守护线程(默认 2 个)。提交的任务按优先级
    被线程取出执行，失败可自动重试；支持等待全部完成与优雅关闭。
    """

    def __init__(self, num_workers: int = 2):
        """构造执行器并启动工作线程。

        参数:
            num_workers (int): 工作线程数量，默认 2
        """
        self._queue = queue.PriorityQueue()
        self._tasks: dict[str, ShadowTask] = {}
        self._lock = threading.Lock()
        self._running = True
        self._workers = []

        # 启动守护线程，线程会持续从队列取任务执行
        for i in range(num_workers):
            t = threading.Thread(target=self._worker_loop, daemon=True, name=f"ShadowWorker-{i}")
            t.start()
            self._workers.append(t)
            logger.info("ShadowWorker-{} started", i)

    def submit(self, task: ShadowTask) -> str:
        """提交一个任务到队列，返回其 task_id。

        先将任务登记进 `_tasks`，再将 `(优先级数值, task_id)` 放入优先队列，
        使高优先级任务更早被消费。

        参数:
            task (ShadowTask): 待提交的任务对象

        返回:
            str: 该任务的 id(便于后续查询状态)

        异常:
            无
        适用场景:
            - 业务侧构造 `ShadowTask` 后调用提交
        """
        with self._lock:
            self._tasks[task.id] = task
        self._queue.put((task.priority.value, task.id))
        logger.debug("Task submitted: {} ({})", task.name, task.id)
        return task.id

    def get_status(self, task_id: str) -> Optional[ShadowTask]:
        """按 task_id 查询任务对象。

        参数:
            task_id (str): 任务 id

        返回:
            ShadowTask | None: 命中的任务对象，或 None

        异常:
            无
        """
        return self._tasks.get(task_id)

    def wait_all(self, timeout: Optional[float] = None):
        """阻塞等待所有任务结束(完成或失败)。

        轮询 `_tasks`，直到没有处于 pending/running 状态的任务；若给定
        `timeout` 则在超时后强制返回，避免无限等待。

        参数:
            timeout (float, 可选): 最长等待秒数，None 表示不限时

        返回:
            None

        异常:
            无
        适用场景:
            - 需要确保所有后台任务落地后再继续(如优雅关闭前)
        """
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
        """关闭 Worker 并退出工作线程。

        置 `_running=False` 让工作循环退出；若 `wait` 为真则 `join` 各线程
        (最多等 5 秒)以完成优雅关闭。

        参数:
            wait (bool): 是否等待线程结束，默认 True

        返回:
            None

        异常:
            无
        """
        self._running = False
        if wait:
            for w in self._workers:
                w.join(timeout=5)
        logger.info("ShadowWorker shut down")

    def _worker_loop(self):
        """工作线程主循环:取任务、执行、处理重试与状态。

        从优先队列取出任务(1 秒超时则回到循环检查 `_running`)，置为
        RUNNING 并执行 `task.fn()`:成功标记 DONE，失败则累加重试次数——
        未达上限重新入队(PENDING)，否则标记 FAILED。无论成败都记录结束时间。
        """
        while self._running:
            try:
                _, task_id = self._queue.get(timeout=1)
            except queue.Empty:
                # 队列空且未关闭时继续轮询，避免空耗 CPU 由 timeout 控制节奏
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
                    # 未超重试上限:重置为待执行并重新入队
                    task.status = TaskStatus.PENDING
                    self._queue.put((task.priority.value, task.id))
                    logger.warning("Task retry {}/{}: {} - {}", task.retries, task.max_retries, task.name, e)
                else:
                    # 重试耗尽:标记为失败
                    task.status = TaskStatus.FAILED
                    logger.error("Task failed: {} - {}", task.name, e)
            finally:
                task.finished_at = datetime.now()


# 全局单例
_default_worker: Optional[ShadowWorker] = None


def get_worker() -> ShadowWorker:
    """获取全局单例影子 Worker(懒初始化)。

    首次调用时创建含 2 个工作线程的 `ShadowWorker`，之后复用同一实例，
    确保全应用共享同一后台线程池。

    参数:
        无

    返回:
        ShadowWorker: 全局唯一的 Worker 实例

    异常:
        无
    适用场景:
        - 应用启动与各处提交任务时统一获取实例
    """
    global _default_worker
    if _default_worker is None:
        _default_worker = ShadowWorker(num_workers=2)
    return _default_worker