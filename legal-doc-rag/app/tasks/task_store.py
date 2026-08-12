"""
task_store.py —— 文档索引异步任务状态存储模块

【作用与功能】
本模块负责文档索引任务的创建、状态跟踪与持久化，以及将 CPU 密集的「PDF 抽取 + BGE-M3
嵌入 + Chroma 建索引」提交到单 worker 后台线程池。任务状态写入 data/tasks.json 并在
模块导入时自动恢复，避免服务重启后误判"请先上传文档"，使上传接口秒回且不阻塞主 API。

【主要组成】
- `_load_tasks` / `_save_tasks`：从磁盘恢复/快照持久化任务状态。
- `create_task`：创建一条 pending 任务并返回 task_id。
- `update_task`：更新任务任意状态字段并刷新时间戳。
- `get_task` / `list_tasks_for_tenant`：读取单任务/某租户全部任务快照。
- `get_active_task_for_tenant` / `has_failed_task_for_tenant`：查询活跃/失败任务。
- `submit_indexing_job`：将索引函数提交到单 worker 线程池异步执行。

【适用场景】
- 文档上传接口受理后创建任务并异步执行索引；前端轮询读取进度与结果。
- 聊天接口在缺乏文档时，据此提示"索引进行中"或"此前提索引失败"。

【依赖关系】
- 上游调用方：上传接口、聊天接口、管理后台。
- 下游依赖：concurrent.futures.ThreadPoolExecutor、JSON 文件（data/tasks.json）、
  BGE-M3 嵌入器、Chroma 向量库。
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
    """启动时从磁盘恢复任务状态。

    读取持久化文件 `tasks.json`，重建内存任务字典 `_TASKS`。为控制文件
    体积增长，只保留仍处于 `pending`/`processing`/`failed` 状态的任务，
    已完成的任务不纳入恢复范围。

    参数:
        无

    返回:
        None

    异常:
        无（读取或解析失败时静默重置为空字典，不影响启动）
    适用场景:
        - 模块导入时自动调用，保证服务重启后未完成任务可继续追踪
    """
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
    """将当前内存中的任务状态快照写回磁盘。

    在持锁下先拷贝 `_TASKS` 快照，再以 JSON 写入 `tasks.json`，使用
    `ensure_ascii=False` 保留中文文件名。写入失败（如磁盘满）仅静默忽略，
    不阻断主业务流程。

    参数:
        无

    返回:
        None

    异常:
        无（异常被捕获并忽略）
    适用场景:
        - 每次任务状态变更后调用，保证持久化与内存一致
    """
    try:
        with _LOCK:
            snapshot = dict(_TASKS)
        with open(_TASKS_FILE, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, ensure_ascii=False, indent=2)
    except Exception:
        # 持久化失败不应影响主流程
        pass


def create_task(tenant_id: str, filename: str) -> str:
    """创建一条文档索引任务并记录初始状态。

    生成 32 位十六进制 `task_id`，在锁内写入 `_TASKS`，状态初始为
    `pending`、阶段 `queued`、进度 0；随后持久化并返回 `task_id`。
    调用方通常接着用 `submit_indexing_job` 提交真正的索引函数。

    参数:
        tenant_id (str): 租户标识，用于隔离任务归属
        filename (str): 待索引的文件名

    返回:
        str: 新建任务的 task_id

    异常:
        无
    适用场景:
        - 文档上传接口受理请求后创建任务并立即返回 task_id
    """
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
    """更新指定任务的任意状态字段并刷新 `updated_at`。

    在锁内对任务字典做就地更新（如 `status`、`stage`、`progress`、`error`、
    `result`），更新时间戳后持久化。若 task_id 不存在则静默跳过。

    参数:
        task_id (str): 目标任务 id
        **fields: 任意需更新的字段键值对（如 status="done", progress=100）

    返回:
        None

    异常:
        无
    适用场景:
        - 索引执行过程中的阶段推进与结果回填
    """
    with _LOCK:
        t = _TASKS.get(task_id)
        if t:
            t.update(fields)
            t["updated_at"] = time.time()
    _save_tasks()


def get_task(task_id: str):
    """获取任务的当前状态快照（深拷贝副本）。

    返回任务字典的副本，避免调用方修改影响内部状态；任务不存在时返回 None。

    参数:
        task_id (str): 目标任务 id

    返回:
        dict | None: 任务状态字典副本，或 None

    异常:
        无
    适用场景:
        - 前端轮询接口读取任务进度与结果
    """
    with _LOCK:
        t = _TASKS.get(task_id)
        return dict(t) if t else None


def list_tasks_for_tenant(tenant_id: str):
    """列出某租户下的全部任务（副本列表）。

    遍历 `_TASKS`，筛选 `tenant_id` 匹配的任务并以字典副本形式返回。

    参数:
        tenant_id (str): 租户标识

    返回:
        list[dict]: 该租户任务状态字典副本组成的列表

    异常:
        无
    适用场景:
        - 管理后台/前端展示某租户的任务历史
    """
    with _LOCK:
        return [dict(t) for t in _TASKS.values() if t["tenant_id"] == tenant_id]


def get_active_task_for_tenant(tenant_id: str):
    """返回该租户最近一个仍在处理中的任务。

    按任务插入顺序逆序遍历，找到第一个状态为 `pending`/`processing` 的任务
    并返回其副本，用于聊天接口给出「索引进行中」之类的友好提示；无则 None。

    参数:
        tenant_id (str): 租户标识

    返回:
        dict | None: 最近活跃任务副本，或 None

    异常:
        无
    适用场景:
        - 聊天接口在缺乏文档时提示用户其文档正在索引中
    """
    with _LOCK:
        for t in reversed(list(_TASKS.values())):
            if t["tenant_id"] == tenant_id and t["status"] in ("pending", "processing"):
                return dict(t)
    return None


def has_failed_task_for_tenant(tenant_id: str, filename: str = None):
    """查询该租户是否存在失败任务，可按文件名过滤。

    遍历 `_TASKS`，匹配 `tenant_id` 且状态为 `failed` 的任务；若提供了
    `filename` 则进一步要求文件名一致。命中即返回该任务副本，否则 None。

    参数:
        tenant_id (str): 租户标识
        filename (str, 可选): 用于进一步限定的文件名

    返回:
        dict | None: 命中的失败任务副本，或 None

    异常:
        无
    适用场景:
        - 上传前/聊天前判断此前是否有同文件索引失败
    """
    with _LOCK:
        for t in _TASKS.values():
            if t["tenant_id"] != tenant_id or t["status"] != "failed":
                continue
            if filename is None or t.get("filename") == filename:
                return dict(t)
    return None


def submit_indexing_job(fn, *args, **kwargs):
    """将 CPU 密集的索引函数提交到后台单 worker 线程池。

    借助模块级 `_EXECUTOR`（单线程）执行 `PDF 抽取 + BGE-M3 嵌入 + 建索引`
    等重活，使上传接口可以立即返回，重活在后台排队、不阻塞主 API，也避免
    对进程内单例模型并发前向。返回 `Future` 供后续取结果/异常。

    参数:
        fn (Callable): 待执行的索引函数
        *args / **kwargs: 透传给 `fn` 的位置与关键字参数

    返回:
        concurrent.futures.Future: 代表后台任务的 Future 对象

    异常:
        无（提交本身不抛异常，错误在 Future 内体现）
    适用场景:
        - 文档上传接口创建任务后，用此函数异步执行索引
    """
    return _EXECUTOR.submit(fn, *args, **kwargs)


# 模块导入时自动加载持久化任务（服务启动即恢复）
_load_tasks()
