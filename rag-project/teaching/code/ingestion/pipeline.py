# ============================================================
# 摄取管线 — 把文档从文件变成向量的全流程编排
#
# 流程：load（解析）→ chunk（切分）→ embed（转向量）→ store（存库）
# 这是 RAG 系统的"写"操作，把知识存进向量数据库
# ============================================================

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger

from teaching.config import settings
from teaching.ingestion.loader import load_document
from teaching.ingestion.chunker import chunk_document, get_tokenizer
from teaching.retrieval.embedder import get_embedder
from teaching.retrieval.vector_store import get_vector_store
from teaching.models import DocumentMeta


def ingest_document(file_path: str, document_id: str | None = None) -> DocumentMeta:
    """摄取一个文档：load → chunk → embed → store。
    
    参数：
        file_path: 文档的完整路径
        document_id: 可选的文档 ID，不传则自动生成
    返回：
        DocumentMeta: 文档的元信息
    """
    doc_id = document_id or _generate_doc_id(file_path)
    logger.info("Ingesting [{}] from {}", doc_id, file_path)

    # ── 第1步：load ──
    # 调用 loader.py 解析文件，返回 LoadedDocument（含所有页面的文本）
    loaded = load_document(file_path)
    logger.info("  Loaded: {} chars, {} pages", loaded.char_count, loaded.page_count)

    # ── 第2步：chunk ──
    # 把长文本切成 800 token 的小块，块间重叠 200 token
    enc = get_tokenizer(settings.embedding_model)
    chunks = chunk_document(
        loaded,
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        tokenizer=enc,
        document_id=doc_id,
    )
    logger.info("  Chunked: {} chunks", len(chunks))

    # ── 第3步：embed ──
    # 把每段文本转成向量（768 维的浮点数数组）
    embedder = get_embedder()
    texts = [c.content for c in chunks]      # 提取所有块的文本
    embeddings = embedder.embed_documents(texts)  # 批量转向量
    logger.info("  Embedded: {} vectors", len(embeddings))

    # ── 第4步：store ──
    # 把（向量 + 原文 + 元信息）存入 ChromaDB
    store = get_vector_store()
    ids = [f"{doc_id}_{i}" for i in range(len(chunks))]  # 为每个块生成唯一 ID
    metadatas = [
        {
            "document_id": doc_id,
            "filename": loaded.filename,
            "chunk_index": c.chunk_index,
            "page_number": c.page_number or 0,
        }
        for c in chunks
    ]
    store.add_embeddings(ids=ids, embeddings=embeddings, documents=texts, metadatas=metadatas)
    logger.info("  Stored: {} vectors", len(embeddings))

    # 返回文档元信息
    return DocumentMeta(
        id=doc_id,
        filename=loaded.filename,
        file_size=Path(file_path).stat().st_size,
        file_type=Path(file_path).suffix.lower(),
        page_count=loaded.page_count,
        char_count=loaded.char_count,
        chunk_count=len(chunks),
        created_at=datetime.now(timezone.utc).isoformat(),
    )


def delete_document(document_id: str) -> bool:
    """从向量数据库删除指定文档的所有块。"""
    return get_vector_store().delete_by_document_id(document_id)


def list_documents() -> list[DocumentMeta]:
    """列出所有已摄取的文档。"""
    return get_vector_store().list_documents()


def _generate_doc_id(file_path: str) -> str:
    """根据文件内容生成稳定的文档 ID（相同文件得到相同 ID）。"""
    path = Path(file_path)
    if path.exists():
        # 取文件内容 SHA256 的前12个字符作为 ID
        h = hashlib.sha256(path.read_bytes()).hexdigest()[:12]
    else:
        h = uuid.uuid4().hex[:12]  # 文件不存在就用随机 ID
    return f"doc_{h}"
