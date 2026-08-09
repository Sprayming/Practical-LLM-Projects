"""
文档索引异步任务状态存储。

任务状态持久化到 JSON 文件（data/tasks.json），服务重启后自动恢复，
避免用户上传文档后因重启/崩溃导致"请先上传文档"的误判。
后台仍使用 ThreadPoolExecutor 单 worker 执行 CPU 密集的
「PDF 抽取 + BGE-M3 嵌入 + Chroma 建索引」，上传接口秒回且主服务不被阻塞。
"""
import threading
import time
import uuid
import json
import os
from concurrent.futures import ThreadPoolExecutor

# 持久化文件路径：项目根目录下的 data/tasks.json
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_DATA_DIR = os.path.join(_PROJECT_ROOT, "data")
_TASKS_FILE = os.path.join(_DATA_DIR, "tasks.json")

os.makedirs(_DATA_DIR, exist_ok=True)

_TASKS: dict = {}
_LOCK = threading.Lock()

# 单 worker：BGE-M3 模型为进程内单例，并发前向对 torch 不安全；
# 上传接口仍秒回，重活在后台线程排队执行，不阻塞主 API。
_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="doc-index")


def _load_tasks() -> None:
    """启动时从磁盘恢复任务状态。"""
    global _TASKS
    if not os.path.exists(_TASKS_FILE):
        _TASKS = {}
        return
    try:
        with open(_TASKS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        # 过滤掉已完成的任务（避免文件无限增长），只保留 pending/processing/failed
        _TASKS = {
            k: v
            for k, v in data.items()
            if v.get("status") in ("pending", "processing", "failed")
        }
    except Exception:
        _TASKS = {}


def _save_tasks() -> None:
    """把当前任务状态写回磁盘。"""
    try:
        with _LOCK:
            snapshot = dict(_TASKS)
        with open(_TASKS_FILE, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, ensure_ascii=False, indent=2)
    except Exception:
        # 持久化失败不应影响主流程
        pass


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
    _save_tasks()
    return task_id


def update_task(task_id: str, **fields):
    """更新任务状态字段。"""
    with _LOCK:
        t = _TASKS.get(task_id)
        if t:
            t.update(fields)
            t["updated_at"] = time.time()
    _save_tasks()


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


def has_failed_task_for_tenant(tenant_id: str, filename: str = None):
    """返回该租户是否存在失败任务，可选按文件名过滤。"""
    with _LOCK:
        for t in _TASKS.values():
            if t["tenant_id"] != tenant_id or t["status"] != "failed":
                continue
            if filename is None or t.get("filename") == filename:
                return dict(t)
    return None


def submit_indexing_job(fn, *args, **kwargs):
    """把 CPU 密集的索引函数提交到后台线程池。"""
    return _EXECUTOR.submit(fn, *args, **kwargs)


# 模块导入时自动加载持久化任务（服务启动即恢复）
_load_tasks()
