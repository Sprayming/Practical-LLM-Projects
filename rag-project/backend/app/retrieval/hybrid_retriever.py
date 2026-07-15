# =+= NEW MODULE - Added 2026-07-15 by Codex =+=\n\n"""
混合检索器 - BM25 稀疏 + Dense 稠密 + RRF 融合 + Cross-Encoder 重排序

使用方式：
  hybrid = HybridRetriever(top_k=5)
  hybrid.build_index()  # 从现有 ChromaDB 构建 BM25 索引
  results = hybrid.retrieve(query)  # 自动走混合检索
"""
import os, re
from typing import Optional
from rank_bm25 import BM25Okapi
from loguru import logger
from app.retrieval.retriever import Retriever, get_retriever
from app.retrieval.vector_store import get_vector_store
from app.models import CitationSource


class CrossEncoderReranker:
    """Cross-Encoder 重排序器 - 对检索结果进行精细排序"""

    def __init__(self, model_name: str = "BAAI/bge-reranker-base"):
        self.model = None
        self.available = False
        try:
            from sentence_transformers import CrossEncoder
            self.model = CrossEncoder(model_name, device="cpu")
            self.available = True
            logger.info("Reranker loaded: {}", model_name)
        except Exception as e:
            logger.warning("Reranker not available: {}", e)

    def rerank(self, query: str, candidates: list[CitationSource], top_k: int = 5) -> list[CitationSource]:
        """对候选结果重排序，返回 top_k"""
        if not self.available or not candidates:
            return candidates[:top_k]
        pairs = [[query, c.content[:512]] for c in candidates]
        scores = self.model.predict(pairs)
        scored = list(zip(candidates, scores))
        scored.sort(key=lambda x: x[1], reverse=True)
        for s, score in scored:
            s.score = round(float(score), 4)
        return [s for s, _ in scored[:top_k]]


class HybridRetriever(Retriever):
    """混合检索器 - BM25 + Dense + RRF + Cross-Encoder"""

    def __init__(self, top_k: int = 5, min_score: float = 0.20):
        super().__init__(top_k, min_score)
        self.bm25: Optional[BM25Okapi] = None
        self._doc_texts: list[str] = []
        self._doc_ids: list[str] = []
        self.reranker = CrossEncoderReranker()
        self.rrf_k = 60

    def build_index(self):
        """从 ChromaDB 获取全部文档，构建 BM25 索引"""
        store = get_vector_store()
        data = store._collection.get(include=["documents", "metadatas"])
        if not data or not data.get("documents"):
            logger.warning("No documents in vector store to build BM25 index")
            return False

        texts = data["documents"]
        ids = data["ids"]
        self._doc_texts = texts
        self._doc_ids = ids

        tokenized = [self._tokenize(t) for t in texts]
        self.bm25 = BM25Okapi(tokenized)
        logger.info("BM25 index built: {} documents", len(texts))
        return True

    def _tokenize(self, text: str) -> list[str]:
        """简单分词：中文单字 + 英文单词"""
        text = text.lower()
        tokens = []
        word = []
        for ch in text:
            if ch.isascii() and ch.isalnum():
                word.append(ch)
            else:
                if word:
                    tokens.append("".join(word))
                    word = []
                if ch.strip():
                    tokens.append(ch)
        if word:
            tokens.append("".join(word))
        return tokens

    def _dense_search(self, query: str, top_k: int) -> list[CitationSource]:
        """稠密检索 - 复用现有 Retriever 逻辑"""
        return super().retrieve(query, top_k=top_k)

    def _sparse_search(self, query: str, top_k: int) -> list[tuple[int, float]]:
        """稀疏检索 - BM25"""
        if not self.bm25:
            return []
        tokenized = self._tokenize(query)
        scores = self.bm25.get_scores(tokenized)
        scored = [(i, scores[i]) for i in range(len(scores)) if scores[i] > 0]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    def _rrf_fuse(
        self,
        dense_results: list[CitationSource],
        sparse_results: list[tuple[int, float]],
    ) -> list[CitationSource]:
        """RRF 加权融合"""
        score_map: dict[str, float] = {}
        doc_map: dict[str, CitationSource] = {}

        for rank, src in enumerate(dense_results):
            key = src.content[:200]
            if key not in doc_map:
                doc_map[key] = src
                score_map[key] = 0.0
            score_map[key] += 1.0 / (self.rrf_k + rank + 1)

        for rank, (doc_idx, bm25_score) in enumerate(sparse_results):
            content = self._doc_texts[doc_idx]
            key = content[:200]
            if key not in doc_map:
                doc_map[key] = CitationSource(
                    document_id=self._doc_ids[doc_idx] if doc_idx < len(self._doc_ids) else "",
                    filename="",
                    content=content,
                    score=0.0,
                    chunk_index=doc_idx,
                )
                score_map[key] = 0.0
            score_map[key] += 1.0 / (self.rrf_k + rank + 1)

        for key in doc_map:
            doc_map[key].score = round(score_map[key], 4)

        result = sorted(doc_map.values(), key=lambda x: x.score, reverse=True)
        return result

    def retrieve(
        self,
        query: str,
        top_k: Optional[int] = None,
        document_ids: Optional[list[str]] = None,
    ) -> list[CitationSource]:
        """混合检索：稠密 → 稀疏 → RRF → Cross-Encoder 重排序"""
        k = top_k or self.top_k

        if not self.bm25:
            logger.warning("BM25 index not built, falling back to dense only")
            return super().retrieve(query, top_k=k, document_ids=document_ids)

        # 1. 稠密检索（取多些候选用做 RRF）
        dense = self._dense_search(query, top_k=k * 3)

        # 2. 稀疏检索
        sparse = self._sparse_search(query, top_k=k * 3)

        logger.debug("Dense: {} results, Sparse: {} results", len(dense), len(sparse))

        # 3. RRF 融合
        fused = self._rrf_fuse(dense, sparse)

        # 4. Cross-Encoder 重排序
        if self.reranker.available:
            results = self.reranker.rerank(query, fused, top_k=k)
            logger.info("Hybrid retrieve: {} candidates -> {} final (reranked)", len(fused), len(results))
        else:
            results = fused[:k]
            logger.info("Hybrid retrieve: {} candidates -> {} final (no reranker)", len(fused), len(results))

        return results


def get_hybrid_retriever() -> HybridRetriever:
    """创建并返回全局 HybridRetriever 实例"""
    retriever = HybridRetriever()
    retriever.build_index()
    return retriever