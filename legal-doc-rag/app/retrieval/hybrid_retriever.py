
"""
混合检索器 - 稠密向量 + 稀疏BM25 + RRF融合 + BGE重排序

流程：
  用户查询
     ↓
  ┌─→ ChromaDB 稠密检索 ──┐
  │                        │
  ├─→ BM25 稀疏检索 ──────┤
  │                        │
  └──── RRF 加权融合 ──────┘
            ↓
     BGE-Reranker 精排
            ↓
       Top-K 结果
"""
import os
import numpy as np
from typing import Optional
from langchain_core.documents import Document
from rank_bm25 import BM25Okapi
from loguru import logger


class Reranker:
    """BGE 交叉编码器重排序（可选，模型加载失败则跳过）"""

    def __init__(self, model_name: str = "BAAI/bge-reranker-base"):
        self.model = None
        self.available = False
        try:
            from sentence_transformers import CrossEncoder
            self.model = CrossEncoder(model_name, device="cpu")
            self.available = True
            logger.info("Reranker loaded: {}", model_name)
        except Exception as e:
            logger.warning("Reranker unavailable (skip): {}", e)

    def rerank(self, query: str, documents: list[Document], top_k: int = 5) -> list[Document]:
        """对检索结果进行重排序"""
        if not self.available or not documents:
            return documents[:top_k]
        pairs = [[query, d.page_content[:512]] for d in documents]
        scores = self.model.predict(pairs)
        scored = list(zip(documents, scores))
        scored.sort(key=lambda x: x[1], reverse=True)
        logger.info("Reranked: top score={:.4f}, bottom={:.4f}", scored[0][1], scored[-1][1])
        return [d for d, _ in scored[:top_k]]


class HybridRetriever:
    """混合检索器 - 稠密(BERT) + 稀疏(BM25) + RRF融合"""

    def __init__(
        self,
        dense_store,
        texts: list[str],
        k: int = 5,
        rrf_k: int = 60,
        dense_weight: float = 1.0,
        sparse_weight: float = 1.0,
        use_reranker: bool = False,
    ):
        self.dense_store = dense_store
        self.texts = texts
        self.k = k
        self.rrf_k = rrf_k
        self.dense_weight = dense_weight
        self.sparse_weight = sparse_weight

        # 初始化 BM25 索引
        tokenized = [self._tokenize(t) for t in texts]
        self.bm25 = BM25Okapi(tokenized)

        # 初始化重排序器
        self.reranker = Reranker() if use_reranker else None

    def _tokenize(self, text: str) -> list[str]:
        """简单中文分词（按字符/词拆分）"""
        text = text.lower()
        # 保留中文和英文单词
        tokens = []
        current = []
        for ch in text:
            if ch.isascii() and (ch.isalnum() or ch in "-_"):
                current.append(ch)
            else:
                if current:
                    tokens.append("".join(current))
                    current = []
                if ch.strip():
                    tokens.append(ch)
        if current:
            tokens.append("".join(current))
        return tokens

    def _dense_search(self, query: str) -> list[tuple[Document, float]]:
        """稠密向量检索 (ChromaDB)"""
        results = self.dense_store.similarity_search_with_score(
            query, k=self.k * 3
        )
        # ChromaDB 返回的是距离，0=最近，越大越远 → 转 similarity
        return [(doc, 1.0 - score / 2.0) for doc, score in results]

    def _sparse_search(self, query: str) -> list[tuple[str, float]]:
        """稀疏检索 (BM25)"""
        tokenized = self._tokenize(query)
        scores = self.bm25.get_scores(tokenized)
        scored = [(i, scores[i]) for i in range(len(scores)) if scores[i] > 0]
        scored.sort(key=lambda x: x[1], reverse=True)
        return [(self.texts[i], s) for i, s in scored[:self.k * 3]]

    def _rrf_fuse(
        self,
        dense_results: list[tuple[Document, float]],
        sparse_results: list[tuple[str, float]],
    ) -> list[Document]:
        """Reciprocal Rank Fusion 融合"""
        doc_map: dict[str, Document] = {}

        for rank, (doc, score) in enumerate(dense_results):
            key = doc.page_content[:200]
            if key not in doc_map:
                doc_map[key] = doc
                doc_map[key].metadata["rrf_score"] = 0.0
            doc_map[key].metadata["rrf_score"] += self.dense_weight / (self.rrf_k + rank + 1)

        for rank, (text, score) in enumerate(sparse_results):
            key = text[:200]
            if key not in doc_map:
                doc_map[key] = Document(page_content=text, metadata={"rrf_score": 0.0})
            doc_map[key].metadata["rrf_score"] += self.sparse_weight / (self.rrf_k + rank + 1)

        result = sorted(doc_map.values(), key=lambda d: d.metadata["rrf_score"], reverse=True)
        return result

    def retrieve(self, query: str, top_k: Optional[int] = None) -> list[Document]:
        """执行混合检索：稠密→稀疏→RRF融合→(可选)重排序"""
        k = top_k or self.k

        # 1. 稠密检索
        dense = self._dense_search(query)
        logger.debug("Dense: top={}, bottom={}", dense[0][1] if dense else 0, dense[-1][1] if dense else 0)

        # 2. 稀疏检索
        sparse = self._sparse_search(query)
        logger.debug("Sparse: {} results", len(sparse))

        # 3. RRF 融合
        fused = self._rrf_fuse(dense, sparse)
        logger.debug("RRF fused: {} -> {}", len(dense) + len(sparse), len(fused))

        # 4. 重排序
        if self.reranker and self.reranker.available:
            fused = self.reranker.rerank(query, fused, k)
        else:
            fused = fused[:k]

        return fused

    def invoke(self, query: str) -> list[Document]:
        """兼容 LangChain retriever 接口"""
        return self.retrieve(query)