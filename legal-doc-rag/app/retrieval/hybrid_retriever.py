
"""
混合检索器 - 稠密向量 + 稀疏BM25 + Elasticsearch + RRF融合 + BGE重排序

流程：
  用户查询
     ↓
  ┌─→ ChromaDB 稠密检索 ──┐
  │                        │
  ├─→ BM25 稀疏检索 ──────┤
  │                        │
  ├─→ Elasticsearch 全文检索 ┤
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
        """初始化 BGE 交叉编码器重排序器（模型加载失败则降级跳过）。

        尝试从 sentence_transformers 加载 CrossEncoder（CPU）。加载失败仅告警、
        available 置 False，后续 rerank 跳过精排直接截断返回，保证链路可用。

        参数:
            model_name: 重排序模型名（默认 "BAAI/bge-reranker-base"）
        """
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
    """混合检索器 - 稠密(BERT) + 稀疏(BM25) + Elasticsearch + RRF融合"""

    def __init__(
        self,
        dense_store,
        texts: list[str],
        k: int = 5,
        rrf_k: int = 60,
        dense_weight: float = 1.0,
        sparse_weight: float = 1.0,
        use_reranker: bool = False,
        use_elasticsearch: bool = False,
        tenant_id: str = None,
        sparse_store: Optional[dict] = None,
        bge_sparse_weight: float = 1.0,
    ):
        """初始化混合检索器，建立各召回通道。

        保存各通道引用与融合参数；基于全部文本构建 BM25 索引（用于稀疏召回）；
        按需初始化重排序器与 Elasticsearch 全文通道（不可用时降级为 None）。

        参数:
            dense_store: 稠密向量库（Chroma 等）的相似度检索接口
            texts: 全部候选文档文本列表（BM25 与稀疏检索的语料）
            k: 最终返回的 Top-K（默认 5）
            rrf_k: RRF 融合常数（默认 60，平滑排名影响）
            dense_weight: 稠密通道 RRF 权重
            sparse_weight: BM25 稀疏通道 RRF 权重
            use_reranker: 是否启用 BGE 重排序精排
            use_elasticsearch: 是否启用 ES 全文召回
            tenant_id: 租户 ID（ES 检索过滤用）
            sparse_store: BGE-M3 稀疏向量 lookup（dict 或对象）
            bge_sparse_weight: BGE-M3 稀疏通道 RRF 权重
        """
        self.dense_store = dense_store
        self.texts = texts
        self.k = k
        self.rrf_k = rrf_k
        self.dense_weight = dense_weight
        self.sparse_weight = sparse_weight
        self.tenant_id = tenant_id
        self.sparse_store = sparse_store
        self.bge_sparse_weight = bge_sparse_weight

        # 初始化 BM25 索引
        tokenized = [self._tokenize(t) for t in texts]
        self.bm25 = BM25Okapi(tokenized)

        # 初始化重排序器
        self.reranker = Reranker() if use_reranker else None

        # 初始化 Elasticsearch (可选)
        self.elasticsearch = None
        if use_elasticsearch:
            try:
                from app.retrieval.elasticsearch_client import get_elasticsearch_client
                self.elasticsearch = get_elasticsearch_client()
                if not self.elasticsearch or not self.elasticsearch.is_available():
                    self.elasticsearch = None
                    logger.warning("Elasticsearch not available, skipping")
            except Exception as e:
                logger.warning("Failed to initialize Elasticsearch: {}", e)
                self.elasticsearch = None

    def _tokenize(self, text: str) -> list[str]:
        """
        Enhanced Chinese/English tokenizer for BM25.

        Features:
        - English word tokenization (lowercase, alphanumeric)
        - Chinese character tokenization
        - Stop word filtering (common Chinese/English stop words)
        - N-gram support for Chinese (bigrams)
        """
        text = text.lower()

        # Common stop words to filter out
        stop_words = {
            # English
            "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
            "have", "has", "had", "do", "does", "did", "will", "would", "could",
            "should", "may", "might", "shall", "can", "need", "dare", "ought",
            "used", "to", "of", "in", "for", "on", "with", "at", "by", "from",
            "as", "into", "through", "during", "before", "after", "above", "below",
            "between", "out", "off", "over", "under", "again", "further", "then",
            "once", "and", "but", "or", "nor", "not", "so", "very", "just",
            # Chinese
            "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都",
            "一", "一个", "上", "也", "很", "到", "说", "要", "去", "你",
            "会", "着", "没有", "看", "好", "自己", "这", "他", "她", "它",
            "们", "那", "些", "什么", "怎么", "吗", "呢", "吧", "啊",
        }

        tokens = []
        current = []

        for ch in text:
            if ch.isascii() and (ch.isalnum() or ch in "-_"):
                current.append(ch)
            else:
                if current:
                    word = "".join(current)
                    if word not in stop_words and len(word) > 1:
                        tokens.append(word)
                    current = []
                if ch.strip() and ch not in stop_words:
                    tokens.append(ch)

        if current:
            word = "".join(current)
            if word not in stop_words and len(word) > 1:
                tokens.append(word)

        # Add Chinese bigrams for better matching
        chinese_chars = [t for t in tokens if not t[0].isascii() and len(t) == 1]
        for i in range(len(chinese_chars) - 1):
            bigram = chinese_chars[i] + chinese_chars[i + 1]
            if bigram not in stop_words:
                tokens.append(bigram)

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

    def _sparse_search_bge(self, query: str) -> list[tuple[str, float]]:
        """稀疏检索 (BGE-M3 SPLADE 词汇权重)。

        与 BM25 互补：BM25 基于词频/逆文档频率，BGE-M3 稀疏是**学习到的**词汇权重，
        对法律术语、法条编号的同义/近义匹配更强。dot-product 打分后参与 RRF 融合。
        sparse_store 为 None 或模型不可用时返回空（降级为 BM25 + 稠密）。
        """
        if not self.sparse_store:
            return []
        try:
            from app.retrieval.bge_m3_embedder import get_bge_m3_model, encode_sparse_direct

            model = get_bge_m3_model()
            if model is None:
                return []
            # 直接使用本模块自计算的确定性 SPLADE 稀疏权重（绕过 FlagEmbedding 偶发丢值路径）
            qsp = encode_sparse_direct(model, [query])[0]
        except Exception as e:  # noqa: BLE001
            logger.warning("BGE-M3 稀疏检索失败，跳过: {}", e)
            return []

        scored = []
        for i, text in enumerate(self.texts):
            dsp = self.sparse_store.get(text[:200])
            if not dsp:
                continue
            score = 0.0
            for tid, qw in qsp.items():
                dw = dsp.get(tid)
                if dw:
                    score += qw * dw
            if score > 0:
                scored.append((i, score))
        scored.sort(key=lambda x: x[1], reverse=True)
        return [(self.texts[i], s) for i, s in scored[: self.k * 3]]

    def _rrf_fuse(
        self,
        dense_results: list[tuple[Document, float]],
        sparse_results: list[tuple[str, float]],
        elasticsearch_results: list[tuple[Document, float]] = None,
        bge_sparse_results: list[tuple[str, float]] = None,
    ) -> list[Document]:
        """Reciprocal Rank Fusion 融合（稠密 + BM25 + 可选 ES + 可选 BGE-M3 稀疏）"""
        doc_map: dict[str, Document] = {}

        for rank, (doc, score) in enumerate(dense_results):
            key = doc.page_content
            if key not in doc_map:
                doc_map[key] = doc
                doc_map[key].metadata["rrf_score"] = 0.0
            doc_map[key].metadata["rrf_score"] += self.dense_weight / (self.rrf_k + rank + 1)

        for rank, (text, score) in enumerate(sparse_results):
            key = text
            if key not in doc_map:
                doc_map[key] = Document(page_content=text, metadata={"rrf_score": 0.0})
            doc_map[key].metadata["rrf_score"] += self.sparse_weight / (self.rrf_k + rank + 1)

        # Elasticsearch results (optional)
        if elasticsearch_results:
            es_weight = 1.0  # Elasticsearch weight
            for rank, (doc, score) in enumerate(elasticsearch_results):
                key = doc.page_content
                if key not in doc_map:
                    doc_map[key] = doc
                    doc_map[key].metadata["rrf_score"] = 0.0
                doc_map[key].metadata["rrf_score"] += es_weight / (self.rrf_k + rank + 1)

        # BGE-M3 稀疏结果 (optional)
        if bge_sparse_results:
            for rank, (text, score) in enumerate(bge_sparse_results):
                key = text
                if key not in doc_map:
                    doc_map[key] = Document(page_content=text, metadata={"rrf_score": 0.0})
                doc_map[key].metadata["rrf_score"] += self.bge_sparse_weight / (
                    self.rrf_k + rank + 1
                )

        result = sorted(doc_map.values(), key=lambda d: d.metadata["rrf_score"], reverse=True)
        return result

    def _elasticsearch_search(self, query: str) -> list[tuple[Document, float]]:
        """Elasticsearch全文检索"""
        if not self.elasticsearch or not self.tenant_id:
            return []

        try:
            results = self.elasticsearch.search(
                query=query,
                tenant_id=self.tenant_id,
                size=self.k * 3,
                min_score=0.1,
            )

            doc_results = []
            for r in results:
                doc = Document(
                    page_content=r["content"],
                    metadata={
                        "source": r["source"],
                        "score": r["score"],
                        "metadata": r.get("metadata", {}),
                    }
                )
                # Normalize score to 0-1 range
                normalized_score = min(1.0, r["score"] / 10.0)
                doc_results.append((doc, normalized_score))

            return doc_results
        except Exception as e:
            logger.warning("Elasticsearch search failed: {}", e)
            return []

    def retrieve(self, query: str, top_k: Optional[int] = None) -> list[Document]:
        """执行混合检索：稠密→BM25→(可选)ES→BGE-M3稀疏→RRF融合→(可选)重排序"""
        k = top_k or self.k

        # 1. 稠密检索
        dense = self._dense_search(query)
        logger.debug("Dense: top={}, bottom={}", dense[0][1] if dense else 0, dense[-1][1] if dense else 0)

        # 2. 稀疏检索 (BM25)
        sparse = self._sparse_search(query)
        logger.debug("Sparse(BM25): {} results", len(sparse))

        # 3. Elasticsearch全文检索 (可选)
        elasticsearch_results = self._elasticsearch_search(query)
        logger.debug("Elasticsearch: {} results", len(elasticsearch_results))

        # 4. BGE-M3 稀疏检索 (可选)
        bge_sparse = self._sparse_search_bge(query)
        logger.debug("Sparse(BGE-M3): {} results", len(bge_sparse))

        # 5. RRF 融合
        fused = self._rrf_fuse(dense, sparse, elasticsearch_results, bge_sparse)
        logger.debug(
            "RRF fused: {} -> {}",
            len(dense) + len(sparse) + len(elasticsearch_results) + len(bge_sparse),
            len(fused),
        )

        # 5. 重排序
        if self.reranker and self.reranker.available:
            fused = self.reranker.rerank(query, fused, k)
        else:
            fused = fused[:k]

        return fused

    def invoke(self, query: str) -> list[Document]:
        """兼容 LangChain retriever 接口"""
        return self.retrieve(query)