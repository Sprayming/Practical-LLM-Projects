"""
sparse_store.py —— BGE-M3 稀疏向量持久化(按租户 + 文档)

【作用与功能】
该模块负责 BGE-M3 稀疏权重的落盘与加载，将每个 chunk 的稀疏字典按租户隔离
存储于 JSON 文件中。检索时按 chunk 文本前 200 字符为 key 重建 lookup，
与 HybridRetriever 的 RRF keying(page_content[:200])保持一致，支撑稀疏召回。

【主要组成】
- `_tenant_dir`:获取(并创建)某租户的稀疏存储目录
- `save_sparse`:保存某文档的稀疏权重字典列表(全局锁防并发写)
- `delete_sparse`:删除指定租户下某文件的稀疏向量
- `load_sparse_lookup`:合并租户全部文档，返回 {key: sparse_dict} 的查询表

【适用场景】
- 场景1:文档上传入库时持久化其 BGE-M3 稀疏向量
- 场景2:HybridRetriever 检索时加载稀疏 lookup 进行 RRF 融合

【依赖关系】
- 上游调用方:入库流程、HybridRetriever(检索稀疏召回)
- 下游依赖:本地文件系统(./sparse_db/{tenant_id}/{filename}.json)
"""
import json
import os
import threading
from typing import Dict, List

SPARSE_DB_DIR = os.getenv("SPARSE_DB_DIR", "./sparse_db")
_lock = threading.Lock()


def _tenant_dir(tenant_id: str) -> str:
    """返回(并创建)某租户的稀疏向量存储目录。"""
    d = os.path.join(SPARSE_DB_DIR, tenant_id)
    os.makedirs(d, exist_ok=True)
    return d


def save_sparse(tenant_id: str, filename: str, items: List[dict]) -> None:
    """items: [{"key": text[:200], "sp": {token_id: weight}}, ...]"""
    path = os.path.join(_tenant_dir(tenant_id), f"{filename}.json")
    with _lock:  # 全局锁防止多进程/多线程并发写同一租户目录
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"items": items}, f, ensure_ascii=False)


def delete_sparse(tenant_id: str, filename: str) -> None:
    """删除某租户下指定文件名对应的稀疏向量文件(忽略异常)。"""
    path = os.path.join(_tenant_dir(tenant_id), f"{filename}.json")
    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception:  # noqa: BLE001
        pass


def load_sparse_lookup(tenant_id: str) -> Dict[str, dict]:
    """合并该租户所有文档，返回 {key: sparse_dict}。文件缺失/损坏返回空字典。"""
    d = os.path.join(SPARSE_DB_DIR, tenant_id)
    lookup: Dict[str, dict] = {}
    if not os.path.isdir(d):
        return lookup
    try:
        for fn in os.listdir(d):
            if not fn.endswith(".json"):
                continue
            with open(os.path.join(d, fn), "r", encoding="utf-8") as f:
                data = json.load(f)
            for it in data.get("items", []):
                lookup[it["key"]] = it["sp"]
    except Exception:  # noqa: BLE001
        pass
    return lookup
