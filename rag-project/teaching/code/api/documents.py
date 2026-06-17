# ============================================================
# 文档管理 API — 上传 / 列表 / 删除文档
# ============================================================

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from loguru import logger

from teaching.config import settings, SUPPORTED_EXTENSIONS
from teaching.models import (
    DocumentMeta,
    DocumentDetail,
    DocumentListResponse,
    UploadResponse,
    DeleteResponse,
)
from teaching.ingestion.pipeline import ingest_document, delete_document, list_documents

# 创建路由器，prefix 表示这个模块的所有路径都以 /api/documents 开头
router = APIRouter(prefix="/api/documents", tags=["Documents"])


@router.get("/", response_model=DocumentListResponse)
async def list_all():
    """GET /api/documents/ — 获取所有已摄取的文档列表。"""
    docs = list_documents()
    return DocumentListResponse(documents=docs, total=len(docs))


@router.post("/upload", response_model=UploadResponse)
async def upload(file: UploadFile = File(...)):
    """POST /api/documents/upload — 上传并摄取文档。
    
    1. 校验文件格式
    2. 保存到临时目录
    3. 调用 ingest_document 执行全流程摄取
    """
    # 校验文件扩展名
    ext = Path(file.filename or "unknown").suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持 {ext}，支持: {', '.join(SUPPORTED_EXTENSIONS)}",
        )

    # 保存上传文件
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    # 用 UUID 防止文件名冲突
    save_path = upload_dir / f"{uuid.uuid4().hex}_{file.filename}"

    content = await file.read()
    if len(content) > settings.max_upload_size_mb * 1024 * 1024:
        raise HTTPException(status_code=400, detail=f"文件超过 {settings.max_upload_size_mb}MB")

    save_path.write_bytes(content)

    # 执行摄取
    try:
        meta = ingest_document(str(save_path))
        return UploadResponse(
            success=True,
            document_id=meta.id,
            filename=meta.filename,
            message=f"'{meta.filename}' 摄取成功，共 {meta.chunk_count} 个文本块",
        )
    except Exception as e:
        # 失败时清理残留文件
        if save_path.exists():
            save_path.unlink()
        logger.error("Ingestion failed: {}", e)
        raise HTTPException(status_code=500, detail=f"摄取失败: {e}")


@router.get("/{document_id}", response_model=DocumentDetail)
async def detail(document_id: str):
    """GET /api/documents/{id} — 查看文档详情。"""
    docs = list_documents()
    for d in docs:
        if d.id == document_id:
            return DocumentDetail(**d.model_dump(), content_preview="")
    raise HTTPException(status_code=404, detail=f"文档 {document_id} 未找到")


@router.delete("/{document_id}", response_model=DeleteResponse)
async def delete(document_id: str):
    """DELETE /api/documents/{id} — 删除文档及其向量索引。"""
    ok = delete_document(document_id)
    if not ok:
        raise HTTPException(status_code=500, detail="删除失败")
    return DeleteResponse(success=True, message=f"文档 {document_id} 已删除")
