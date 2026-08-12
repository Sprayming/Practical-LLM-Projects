"""
documents.py —— 文档上传、索引与预览 API 模块

【作用与功能】
本模块负责文档全生命周期的 HTTP 接口：接收 PDF 上传并进行安全与体积校验，立即创建后台
异步索引任务（避免大文档阻塞主服务），提供任务进度查询、已上传文档列表、PDF 在线预览，
以及管理员删除文档（同步清理稠密向量、稀疏向量与源文件）。它是 RAG 检索链路的数据入口。

【主要组成】
- `upload_document`：上传 PDF 并异步提交索引任务，返回 task_id。
- `_run_indexing`：后台线程执行文本抽取、稀疏/稠密向量化与建库，全程更新任务状态。
- `get_upload_task`：查询索引任务进度（含跨租户越权校验）。
- `list_documents`：列出当前租户已上传的 PDF 文件名。
- `preview_document`：安全地在线预览 PDF（防目录遍历攻击）。
- `delete_document`：管理员删除文档并清理向量与源文件。

【适用场景】
- 用户在知识库页面上传法律文档，系统异步构建可检索向量索引。
- 前端轮询任务进度，索引完成后即可在对话中检索该文档。
- 管理员清理过期或错误文档及其全部向量数据。

【依赖关系】
- 上游调用方：前端知识库上传/管理页面。
- 下游依赖：app.retrieval.embedder_factory、app.processing.multimodal_pipeline、
  app.retrieval.sparse_store、app.security.middleware、app.tasks.task_store、Chroma 向量库。
"""

import os, sys, json, tempfile

# 将项目根目录添加到系统路径中，以便正确导入项目内的其他模块
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import os
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from loguru import logger
from app.retrieval.embedder_factory import create_embedder
from app.processing.multimodal_pipeline import MultimodalPipeline
from langchain_community.vectorstores import Chroma
import app.core.config as cfg
from app.api.auth import get_user_from_token, require_user
from app.security.middleware import get_safe_upload_path, sanitize_filename
from app.tasks.task_store import (
    create_task,
    update_task,
    get_task,
    submit_indexing_job,
)

# 创建 API 路由器实例，统一添加 /api/documents 前缀，并打上 "documents" 标签用于文档分类
router = APIRouter(prefix="/api/documents", tags=["documents"])

# 允许上传的文件扩展名白名单
ALLOWED_EXTENSIONS = {".pdf"}

# 最大文件大小限制：100MB
MAX_FILE_SIZE = 100 * 1024 * 1024


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    user: dict = Depends(require_user),
):
    """
    上传文档接口。
    
    接收前端上传的 PDF 文件，进行安全与大小校验后保存到租户目录，
    并立即创建后台索引任务返回 task_id，避免大文档索引阻塞主服务。
    
    参数：
        file (UploadFile): FastAPI 注入的上传文件对象。
        user (dict): 依赖注入获取的当前登录用户信息，用于提取 tenant_id。
        
    异常：
        HTTPException: 缺少文件名抛出 400；文件类型不允许抛出 400；文件过大抛出 413。
        
    返回：
        dict: 包含成功标志、任务ID、文件名、初始状态和提示消息。
    """
    tenant_id = user["tenant_id"]

    # 1. 校验文件扩展名是否在白名单内
    if not file.filename:
        raise HTTPException(400, "No filename provided")
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"File type not allowed. Allowed: {ALLOWED_EXTENSIONS}")

    # 2. 读取文件内容并校验体积大小
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(413, f"File too large. Maximum size: {MAX_FILE_SIZE // (1024*1024)}MB")

    # 3. 获取安全的文件存储路径（防止目录遍历攻击）并写入磁盘
    file_path = get_safe_upload_path(cfg.UPLOAD_DIR, tenant_id, file.filename)
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, "wb") as f:
        f.write(content)

    # 4. 提交异步索引任务：立即返回 task_id，CPU 密集的抽取+嵌入+建索引在后台线程执行，
    # 不阻塞主服务（避免大文档上传卡死整个 uvicorn 进程）。
    task_id = create_task(tenant_id, file.filename)
    submit_indexing_job(_run_indexing, task_id, tenant_id, file_path, file.filename)

    return {
        "success": True,
        "task_id": task_id,
        "filename": file.filename,
        "status": "pending",
        "message": "文档已接收，正在后台索引，请通过 GET /api/documents/task/{task_id} 查询进度",
    }


def _run_indexing(task_id: str, tenant_id: str, file_path: str, filename: str):
    """
    后台线程执行函数：抽取文本 + 生成向量 + 建立索引，全程更新任务状态。
    
    该函数在后台 Worker 线程中运行，处理流程分为四个阶段：
    1. extracting (文本抽取)：使用 MultimodalPipeline 解析 PDF。
    2. embedding (稀疏向量化)：尝试生成并持久化 BGE-M3 稀疏向量（用于混合检索增强）。
    3. building_index (稠密向量化与建库)：调用 LangChain 与 ChromaDB 构建稠密向量索引。
    4. completed (完成)：更新任务状态为 done。
    任何环节出现致命错误，将任务状态标记为 failed。
    
    参数：
        task_id (str): 当前索引任务的唯一标识。
        tenant_id (str): 租户ID，用于数据隔离存储。
        file_path (str): 已上传文件的绝对路径。
        filename (str): 文件原始名称，用于在向量库中标记来源。
    """
    try:
        # 阶段1：文本抽取
        update_task(task_id, status="processing", stage="extracting", progress=10)
        pipeline = MultimodalPipeline()
        chunks = pipeline.process(file_path)
        if not chunks:
            update_task(task_id, status="failed", stage="extracting", progress=100,
                        error="No text extracted from PDF")
            return

        texts = [c.text for c in chunks]
        if not texts:
            update_task(task_id, status="failed", stage="extracting", progress=100,
                        error="No text extracted from PDF")
            return

        # 阶段2：生成并持久化 BGE-M3 稀疏向量（失败不影响稠密入库，检索时自动降级）
        update_task(task_id, stage="embedding", progress=40)
        embedder = create_embedder()
        try:
            from app.retrieval.bge_m3_embedder import BGEM3Embedder
            from app.retrieval.sparse_store import save_sparse

            # 仅当配置的嵌入器为 BGE-M3 时才生成稀疏向量
            if isinstance(embedder, BGEM3Embedder):
                sp_items = [
                    {"key": t[:200], "sp": sp}
                    for t, sp in zip(texts, embedder.encode_sparse(texts))
                ]
                save_sparse(tenant_id, filename, sp_items)
                logger.info("BGE-M3 稀疏向量已持久化: {} chunks", len(sp_items))
        except Exception as e:  # noqa: BLE001
            logger.warning("稀疏向量生成失败（不影响稠密入库）: {}", e)

        # 阶段3：构建稠密向量索引并存入 ChromaDB
        update_task(task_id, stage="building_index", progress=70)
        persist_dir = os.path.join(cfg.CHROMA_PERSIST_DIR, tenant_id)
        vector_store = Chroma.from_texts(
            texts=texts,
            embedding=embedder,
            metadatas=[{"source": filename, "chunk": i} for i in range(len(texts))],
            persist_directory=persist_dir,
        )
        vector_store.persist()

        # 阶段4：全部完成
        update_task(
            task_id,
            status="done",
            stage="completed",
            progress=100,
            result={"filename": filename, "chunks": len(texts), "tenant_id": tenant_id},
        )
    except Exception as e:  # noqa: BLE001
        # 捕获所有未预料到的异常，防止后台线程静默崩溃，将任务标记为失败
        logger.exception("文档索引失败: {}", e)
        update_task(task_id, status="failed", stage="error", progress=100, error=str(e))


@router.get("/task/{task_id}")
def get_upload_task(task_id: str, user: dict = Depends(require_user)):
    """
    查询文档索引任务的进度与状态。
    
    前端轮询此接口以获取大文档后台解析的实时进度。
    
    参数：
        task_id (str): 路径参数，上传时返回的任务 ID。
        user (dict): 依赖注入获取的当前登录用户信息。
        
    异常：
        HTTPException: 任务不存在抛出 404；无权查看其他租户任务抛出 403。
        
    返回：
        dict: 包含任务状态、进度、当前阶段及错误信息的任务详情。
    """
    task = get_task(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    # 安全校验：防止跨租户越权查询任务进度
    if task["tenant_id"] != user["tenant_id"]:
        raise HTTPException(403, "Forbidden")
    return task


@router.get("")
def list_documents(user: dict = Depends(require_user)):
    """
    获取当前租户已上传的文档列表。
    
    仅列出上传目录中的 PDF 文件名，不包含索引状态等详细信息。
    
    参数：
        user (dict): 依赖注入获取的当前登录用户信息，用于提取 tenant_id。
        
    返回：
        dict: 包含文档文件名列表 documents。
    """
    tenant_id = user["tenant_id"]
    upload_dir = os.path.join(cfg.UPLOAD_DIR, tenant_id)
    if not os.path.exists(upload_dir):
        return {"documents": []}
    files = [f for f in os.listdir(upload_dir) if f.endswith(".pdf")]
    return {"documents": files}


@router.get("/preview/{filename}")
async def preview_document(filename: str, user: dict = Depends(require_user)):
    """
    在线预览 PDF 文档。
    
    对文件名进行安全清洗和路径校验后，以 FileResponse 流式返回 PDF 文件供前端渲染。
    
    参数：
        filename (str): 路径参数，待预览的文件名。
        user (dict): 依赖注入获取的当前登录用户信息，用于提取 tenant_id。
        
    异常：
        HTTPException: 文件名非法抛出 400；文件不存在抛出 404。
        
    返回：
        FileResponse: FastAPI 的文件响应对象，Content-Type 为 application/pdf。
    """
    tenant_id = user["tenant_id"]

    # 清洗文件名，防止目录遍历攻击（如 ../../etc/passwd）
    safe_filename = sanitize_filename(filename)
    upload_dir = os.path.join(cfg.UPLOAD_DIR, tenant_id)
    file_path = os.path.join(upload_dir, safe_filename)

    # 二次验证合成后的路径是否仍在合法的上传目录内
    from app.security.middleware import is_safe_path
    if not is_safe_path(upload_dir, file_path):
        raise HTTPException(400, "Invalid filename")

    # 检查文件是否存在
    if not os.path.exists(file_path):
        raise HTTPException(404, "Document not found")

    # 返回文件流用于前端预览
    from fastapi.responses import FileResponse
    return FileResponse(
        path=file_path,
        media_type="application/pdf",
        filename=safe_filename,
    )


@router.delete("/{filename}")
def delete_document(filename: str, user: dict = Depends(require_user)):
    """
    删除指定文档及其关联的所有向量数据（仅管理员可操作）。
    
    执行删除操作包括：
    1. 删除源 PDF 文件。
    2. 删除 ChromaDB 中的稠密向量数据。
    3. 删除 BGE-M3 稀疏向量数据文件。
    
    参数：
        filename (str): 路径参数，待删除的文件名。
        user (dict): 依赖注入获取的当前登录用户信息，用于提取 tenant_id 和 role。
        
    异常：
        HTTPException: 非管理员抛出 403；文件名非法抛出 400；文件不存在抛出 404。
        
    返回：
        dict: 包含成功标志和确认消息。
    """
    tenant_id = user["tenant_id"]
    role = user.get("role", "user")

    # 权限校验：仅超级管理员可执行删除
    if role != "super_admin":
        raise HTTPException(403, "仅管理员可以删除文档")

    # 清洗文件名，防止目录遍历攻击
    safe_filename = sanitize_filename(filename)
    upload_dir = os.path.join(cfg.UPLOAD_DIR, tenant_id)
    file_path = os.path.join(upload_dir, safe_filename)

    # 二次验证路径安全性
    from app.security.middleware import is_safe_path
    if not is_safe_path(upload_dir, file_path):
        raise HTTPException(400, "Invalid filename")

    # 步骤1：删除磁盘上的源 PDF 文件
    deleted = False
    if os.path.exists(file_path):
        os.remove(file_path)
        deleted = True

    # 步骤2：从 ChromaDB 删除对应的稠密向量数据。
    # 注意：删除只需按 source 元数据过滤，无需加载 embedding 模型
    # （原先 create_embedder() 会触发 BGE-M3 加载，慢且易在内存压力下失败，
    # 失败被静默吞掉会导致向量残留、文档"删不干净"）。
    persist_dir = os.path.join(cfg.CHROMA_PERSIST_DIR, tenant_id)
    if os.path.exists(persist_dir):
        try:
            import chromadb

            client = chromadb.PersistentClient(path=persist_dir)
            col = client.get_or_create_collection("langchain")
            # source 在历史上可能以原始名或 sanitize 名存储，两者都尝试删除以确保彻底清理
            for src in (filename, safe_filename):
                try:
                    col.delete(where={"source": src})
                except Exception:
                    pass
        except Exception:
            pass

    # 步骤3：同步删除 BGE-M3 稀疏向量文件
    try:
        from app.retrieval.sparse_store import delete_sparse

        delete_sparse(tenant_id, filename)
    except Exception:
        pass

    # 如果源文件不存在且未被执行删除，则向客户端返回 404
    if not deleted:
        raise HTTPException(404, "Document not found")

    return {"success": True, "message": f"{filename} 已删除"}
