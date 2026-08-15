"""
app/main/events.py —— 事件钩子模块

【作用与功能】
负责设置应用启动和关闭时的事件钩子。
"""

from fastapi import FastAPI
import os
import asyncio
from loguru import logger
from app.core import config as cfg
from app.worker.webhook import get_webhook_manager

def setup_events(app: FastAPI):
    """
    设置应用事件钩子

    Args:
        app (FastAPI): FastAPI 应用实例
    """
    @app.on_event("startup")
    async def startup_event():
        """
        应用启动事件钩子。
        """
        webhook_manager = get_webhook_manager()
        webhook_manager.start()
        _recover_incomplete_indexing()
        # 预热嵌入/重排序模型:避免首个用户请求在事件循环里阻塞加载(加载耗时数秒),
        # 高并发下首个请求若触发模型加载会卡住事件循环,预热可消除这一抖动。
        await asyncio.to_thread(_warmup_models)

    @app.on_event("shutdown")
    async def shutdown_event():
        """
        应用关闭事件钩子。
        """
        webhook_manager = get_webhook_manager()
        webhook_manager.stop()


def _warmup_models():
    """启动预热:提前加载嵌入模型与重排序器(失败不影响主流程,仅告警)。"""
    try:
        from app.retrieval.embedder_factory import create_embedder
        create_embedder()
        logger.info("模型预热完成: embedder")
    except Exception as e:  # noqa: BLE001
        logger.warning("模型预热失败(embedder),首个请求将按需加载: {}", e)
    try:
        from app.retrieval.hybrid_retriever import Reranker
        Reranker()
        logger.info("模型预热完成: reranker")
    except Exception as e:  # noqa: BLE001
        logger.warning("模型预热失败(reranker),首个请求将按需加载: {}", e)


def _recover_incomplete_indexing():
    """
    启动时扫描上传目录，对尚未完成向量化的文档自动重新提交索引任务。

    该函数用于处理服务意外重启或崩溃后的数据一致性问题。
    它会遍历所有租户的上传目录，比对向量数据库中已存在的记录，
    找出遗漏的 PDF 文件并重新创建索引任务提交到后台 Worker 执行。

    工作流程:
    1. 遍历上传目录下的各个租户文件夹。
    2. 提取该租户文件夹下所有的 PDF 文件名。
    3. 检查向量数据库，获取已成功索引的文件来源列表。
    4. 检查任务队列，获取当前正在处理或等待中的文件列表，防止重复提交。
    5. 对于既不在向量库也不在活动任务中的文件，创建新的索引任务并提交。
    """
    import os
    from app.core import config as cfg
    from app.tasks.task_store import (
        create_task,
        submit_indexing_job,
        list_tasks_for_tenant,
    )
    from app.api.documents import _run_indexing
    from langchain_community.vectorstores import Chroma
    from app.retrieval.embedder_factory import create_embedder

    # 如果全局上传目录不存在，直接返回
    if not os.path.exists(cfg.UPLOAD_DIR):
        return

    # 延迟初始化 embedder，避免在不需要恢复时占用资源
    embedder = None

    # 遍历上传目录下的所有项(预期为租户ID文件夹)
    for tenant_id in os.listdir(cfg.UPLOAD_DIR):
        tenant_upload_dir = os.path.join(cfg.UPLOAD_DIR, tenant_id)

        # 跳过非目录文件
        if not os.path.isdir(tenant_upload_dir):
            continue

        # 获取当前租户目录下所有的 PDF 文件
        pdfs = [f for f in os.listdir(tenant_upload_dir) if f.lower().endswith(".pdf")]
        if not pdfs:
            continue

        # 检查向量库中已有的文档记录，避免重复索引
        persist_dir = os.path.join(cfg.CHROMA_PERSIST_DIR, tenant_id)
        existing_sources = set()
        if os.path.exists(persist_dir):
            try:
                # 懒加载:仅在确认有向量库目录时才初始化 embedder
                if embedder is None:
                    embedder = create_embedder()
                store = Chroma(
                    embedding_function=embedder,
                    persist_directory=persist_dir,
                )
                # 从 Chroma 底层 collection 获取元数据，提取 source 字段
                metas = store._collection.get(include=["metadatas"]).get("metadatas") or []
                existing_sources = {m.get("source") for m in metas if m.get("source")}
            except Exception:
                # 如果读取向量库发生异常，视作没有已存在记录，后续会尝试重新索引
                existing_sources = set()

        # 检查任务队列，避免与已有未完成任务重复提交
        active_files = {
            t["filename"]
            for t in list_tasks_for_tenant(tenant_id)
            if t["status"] in ("pending", "processing")
        }

        # 遍历所有 PDF 文件，提交缺失的索引任务
        for filename in pdfs:
            # 如果文件已成功索引，或正在索引中，则跳过
            if filename in existing_sources:
                continue
            if filename in active_files:
                continue

            # 符合条件:文件存在但未被索引且无活动任务，重新提交索引
            file_path = os.path.join(tenant_upload_dir, filename)
            task_id = create_task(tenant_id, filename)
            submit_indexing_job(_run_indexing, task_id, tenant_id, file_path, filename)
