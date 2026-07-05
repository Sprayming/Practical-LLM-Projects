# ============================================================
# 文档管理 API - 上传/列表/删除
# 把用户上传的文档经过 加载 → 切分 → 嵌入 → 存入向量库
# ============================================================

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from loguru import logger

from app.config import settings
from app.models import (
    DeleteResponseModel,
    DocumentDetailModel,
    DocumentListResponseModel,
    DocumentMetaModel,
    UploadResponseModel,
)
from app.ingestion.loader import load_document
from app.ingestion.chunker import DocumentChunker, get_tokenizer
from app.retrieval.embedder import Embedder
from app.retrieval.vector_store import get_vector_store

router = APIRouter(prefix="/api/documents", tags=["Documents"])

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md", ".csv", ".xlsx", ".pptx", ".html"}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB


@router.post("/upload", response_model=UploadResponseModel)
async def upload_document(file: UploadFile = File(...)):
    """上传文档 → 加载 → 切分 → 嵌入 → 存入向量库"""
    # 1. 校验文件
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"不支持的文件格式: {ext}")

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="文件超过 50MB 限制")

    # 2. 保存临时文件
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    doc_id = str(uuid.uuid4())
    temp_path = upload_dir / f"{doc_id}{ext}"
    temp_path.write_bytes(content)
    logger.info("文件已保存: {}", temp_path)

    try:
        # 3. 加载文档
        loaded_doc = load_document(str(temp_path))

        # 4. 切分文档
        tokenizer = get_tokenizer()
        chunker = DocumentChunker(
            chunk_size=settings.chunk_size,
            tokenizer=tokenizer,
        )
        chunks = chunker.chunk(loaded_doc)

        if not chunks:
            raise HTTPException(status_code=400, detail="文档切分后无有效内容")

        # 5. 生成嵌入向量
        embedder = Embedder()
        texts = [chunk.content for chunk in chunks]
        embeddings = embedder.embed_document(texts)

        # 6. 存入向量库
        store = get_vector_store()
        chunk_ids = [f"{doc_id}_{i}" for i in range(len(chunks))]
        metadatas = [
            {
                "document_id": doc_id,
                "filename": file.filename,
                "page_number": chunk.page_number or 1,
                "chunk_index": chunk.chunk_index,
            }
            for chunk in chunks
        ]
        store.add_embeddings(
            ids=chunk_ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas,
        )

        logger.info("文档上传完成: {}, chunks={}", file.filename, len(chunks))
        return UploadResponseModel(
            success=True,
            document_id=doc_id,
            filename=file.filename,
            message=f"上传成功，共 {len(chunks)} 个文本块",
        )

    except Exception as e:
        logger.error("文档处理失败: {}", e)
        raise HTTPException(status_code=500, detail=f"文档处理失败: {str(e)}")
    finally:
        if temp_path.exists():
            temp_path.unlink()


@router.get("/", response_model=DocumentListResponseModel)
async def list_documents():
    """获取文档列表"""
    try:
        store = get_vector_store()
        docs = store.list_documents()
        return DocumentListResponseModel(documents=docs, total=len(docs))
    except Exception as e:
        logger.error("获取文档列表失败: {}", e)
        raise HTTPException(status_code=500, detail="获取文档列表失败")


@router.delete("/{document_id}", response_model=DeleteResponseModel)
async def delete_document(document_id: str):
    """删除文档及其向量"""
    try:
        store = get_vector_store()
        success = store.delete_by_document_id(document_id)
        if success:
            return DeleteResponseModel(
                success=True, message=f"文档 {document_id} 已删除"
            )
        else:
            raise HTTPException(status_code=404, detail="文档未找到")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("删除文档失败: {}", e)
        raise HTTPException(status_code=500, detail="删除文档失败")
