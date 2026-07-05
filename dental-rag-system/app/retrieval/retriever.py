# ============================================================
# 检索器 — 把用户问题转成向量，去 ChromaDB 搜最相关的文本块
#
# 这是 RAG 的"读"操作
# 流程：用户问题 → 向量化 → 搜向量库 → 过滤低分结果 → 返回
# =============================================================

from __future__ import annotations

from typing import Optional

from loguru import logger

from app.config import settings
from app.retrieval.embedder import get_embedder          # 嵌入器
from app.retrieval.vector_store import get_vector_store    # 向量库
from app.models import CitationSourceModel


class Retriever:
    """检索器：把 query 转为向量并在向量库中搜索。"""
    
    def __init__(self, top_k: int = 5, min_score: float = 0.20) -> None:
        self.top_k = top_k
        self.min_score = min_score
        self._embedder = get_embedder()
        self._vector_store = get_vector_store()


    def retrieve(
        self,
        query: str,                          # 用户问题
        top_k: Optional[int] = None,         # 本次搜索要多少结果
        document_ids: Optional[list[str]] = None,  # 限定搜索范围
        query_embedding: Optional[list[float]] = None,  # 查询向量
    ) -> list[CitationSourceModel]:
        """
        把用户问题转成向量，去 ChromaDB 搜最相关的文本块。
        1. 把用户问题转成向量
        2. 在向量库中搜索
        3. 过滤低分结果
        4. 返回
        """

        k=top_k or self.top_k
        logger.info("检索器：搜索 {} 个结果", k,query[:80])

        # 1. 把用户问题转成向量
        query_embedding = self._embedder.embed_query(query)

        # 2. 构建过滤条件（指定文档范围）
        where = {"document_id": {"$in": document_ids}} if document_ids else None
        
        # 3. 去向量库去搜索
        results = self._vector_store.search(query_embedding, top_k=k, where=where)

        # 4. 过滤低分结果，并组装结结果
        sources :list[CitationSourceModel] = [] # 组装成 CitationSource
        for id, score, document, metadata in results:
            if score < self.min_score: # 过滤低分结果
                continue # logger.info("检索器：过滤低分结果，id={}", document_id)
            sources.append(CitationSourceModel(
                document_id=metadata.get("document_id",""),
                filename=metadata.get("filename",""),
                page=metadata.get("page",""),
                chunk_index=metadata.get("chunk_index",0),
                document= document[:500],
                score=score,
            ))
        return sources
    

    #单例
_retriever: Optional[Retriever] = None


#   
def get_retriever() -> Retriever:
    global _retriever
    if not _retriever:
        _retriever = Retriever(
            top_k=settings.retrieval_top_k,
            min_score=settings.retrieval_min_score,
        )
    return _retriever


