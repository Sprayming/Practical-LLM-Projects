# ============================================================
# 检索器 — 把用户问题转成向量，去 ChromaDB 搜最相关的文本块
#
# 这是 RAG 的"读"操作
# 流程：用户问题 → 向量化 → 搜向量库 → 过滤低分结果 → 返回
# ============================================================

from __future__ import annotations

from typing import Optional

from loguru import logger

from app.config import settings
from app.retrieval.embedder import get_embedder          # 嵌入器
from app.retrieval.vector_store import get_vector_store    # 向量库
from app.models import CitationSource


class Retriever:
    """检索器：把 query 转为向量并在向量库中搜索。"""

    def __init__(self, top_k: int = 5, min_score: float = 0.20) -> None:
        self.top_k = top_k                  # 返回多少结果
        self.min_score = min_score          # 最低分数阈值
        self._embedder = get_embedder()      # 嵌入器实例
        self._store = get_vector_store()     # 向量库实例

    def retrieve(
        self,
        query: str,                          # 用户问题
        top_k: Optional[int] = None,         # 本次搜索要多少结果
        document_ids: Optional[list[str]] = None,  # 限定搜索范围
    ) -> list[CitationSource]:
        """检索相关上下文。
        
        1. 把问题转成向量
        2. 去 ChromaDB 搜最相似的 top_k 个块
        3. 过滤掉分数低于 min_score 的结果
        4. 组装成 CitationSource 列表返回
        """
        k = top_k or self.top_k
        logger.info("Retrieve top_k={}: {}", k, query[:80])

        # 第1步：嵌入查询
        qvec = self._embedder.embed_query(query)

        # 第2步：构建过滤条件（如果指定了文档范围）
        where = {"document_id": {"$in": document_ids}} if document_ids else None

        # 第3步：去向量库搜索
        results = self._store.search(query_embedding=qvec, top_k=k, where=where)

        # 第4步：组装结果
        sources: list[CitationSource] = []
        for chunk_id, score, content, meta in results:
            if score < self.min_score:
                continue  # 分数太低的不要
            sources.append(CitationSource(
                document_id=meta.get("document_id", ""),
                filename=meta.get("filename", ""),
                page_number=meta.get("page_number"),
                chunk_index=meta.get("chunk_index", 0),
                content=content[:500],  # 截取前500字符，避免传给 LLM 的内容太长
                score=score,
            ))
        return sources


# ── 单例 ──
_retriever: Optional[Retriever] = None


def get_retriever() -> Retriever:
    global _retriever
    if _retriever is None:
        _retriever = Retriever(
            top_k=settings.retrieval_top_k,
            min_score=settings.retrieval_min_score,
        )
    return _retriever
