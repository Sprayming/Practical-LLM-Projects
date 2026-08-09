"""
文档索引异步任务状态存储。

进程内内存字典（轻量定位：单实例，重启即清空）。配合 ThreadPoolExecutor
在后台线程执行 CPU 密集的「PDF 抽取 + BGE-M3 嵌入 + Chroma 建索引」，
使上传接口秒回，主服务事件循环不被阻塞（解决大文档上传卡死整个进程的问题）。
"""
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

_TASKS: dict = {}
_LOCK = threading.Lock()

# 单 worker：BGE-M3 模型为进程内单例，并发前向对 torch 不安全；
# 上传接口仍秒回，重活在后台线程排队执行，不阻塞主 API。
_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="doc-index")


def create_task(tenant_id: str, filename: str) -> str:
    """创建一条索引任务，返回 task_id。"""
    task_id = uuid.uuid4().hex
    with _LOCK:
        _TASKS[task_id] = {
            "task_id": task_id,
            "tenant_id": tenant_id,
            "filename": filename,
            "status": "pending",      # pending -> processing -> done | failed
            "stage": "queued",       # queued/extracting/embedding/building_index/completed/error
            "progress": 0,           # 0-100
            "error": None,
            "result": None,
            "created_at": time.time(),
            "updated_at": time.time(),
        }
    return task_id


def update_task(task_id: str, **fields):
    """更新任务状态字段。"""
    with _LOCK:
        t = _TASKS.get(task_id)
        if t:
            t.update(fields)
            t["updated_at"] = time.time()


def get_task(task_id: str):
    """获取任务快照（副本）。"""
    with _LOCK:
        t = _TASKS.get(task_id)
        return dict(t) if t else None


def list_tasks_for_tenant(tenant_id: str):
    """列出某租户的所有任务（副本）。"""
    with _LOCK:
        return [dict(t) for t in _TASKS.values() if t["tenant_id"] == tenant_id]


def get_active_task_for_tenant(tenant_id: str):
    """返回该租户最近一个仍在处理中的任务（用于 chat 友好提示）。"""
    with _LOCK:
        for t in reversed(list(_TASKS.values())):
            if t["tenant_id"] == tenant_id and t["status"] in ("pending", "processing"):
                return dict(t)
    return None


def submit_indexing_job(fn, *args, **kwargs):
    """把 CPU 密集的索引函数提交到后台线程池。"""
    return _EXECUTOR.submit(fn, *args, **kwargs)
