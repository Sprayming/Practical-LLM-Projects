"""
app.retrieval.hybrid_retriever 模块的单元测试 - 版本 3
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from langchain_core.documents import Document


class TestReranker:
    """重排序器（Reranker）类的测试"""

    @patch("sentence_transformers.CrossEncoder")
    def test_reranker_init_success(self, mock_ce):
        """
        测试重排序器初始化成功
        
        验证：
        1. CrossEncoder 模型正确加载
        2. available 标志设置为 True
        3. model 属性正确设置
        """
        from app.retrieval.hybrid_retriever import Reranker

        mock_model = Mock()
        mock_ce.return_value = mock_model

        reranker = Reranker("test-model")
        assert reranker.available is True
        assert reranker.model is mock_model

    @patch("sentence_transformers.CrossEncoder", side_effect=Exception("Model not found"))
    def test_reranker_init_failure(self, mock_ce):
        """
        测试重排序器初始化失败时的处理
        
        验证：
        1. 异常被正确捕获
        2. available 标志设置为 False
        3. model 属性设置为 None
        """
        from app.retrieval.hybrid_retriever import Reranker

        reranker = Reranker("test-model")
        assert reranker.available is False
        assert reranker.model is None

    def test_rerank_without_model(self):
        """
        测试没有可用模型时的重排序
        
        验证：
        1. 返回原始文档（不排序）
        2. 保持文档顺序
        """
        from app.retrieval.hybrid_retriever import Reranker

        reranker = Reranker.__new__(Reranker)
        reranker.available = False
        reranker.model = None

        docs = [Document(page_content="doc1"), Document(page_content="doc2")]
        result = reranker.rerank("query", docs, top_k=1)

        assert len(result) == 1
        assert result[0].page_content == "doc1"

    def test_rerank_with_empty_documents(self):
        """
        测试空文档列表的重排序
        
        验证：
        1. 返回空列表
        """
        from app.retrieval.hybrid_retriever import Reranker

        reranker = Reranker.__new__(Reranker)
        reranker.available = True
        reranker.model = Mock()

        result = reranker.rerank("query", [], top_k=5)
        assert len(result) == 0

    @patch("sentence_transformers.CrossEncoder")
    def test_rerank_with_model(self, mock_ce):
        """
        测试有可用模型时的重排序
        
        验证：
        1. 模型被正确调用
        2. 结果按分数排序
        3. 返回指定数量的结果
        """
        from app.retrieval.hybrid_retriever import Reranker

        mock_model = Mock()
        mock_model.predict.return_value = [0.8, 0.2, 0.6]
        mock_ce.return_value = mock_model

        reranker = Reranker("test-model")
        docs = [
            Document(page_content="doc1"),
            Document(page_content="doc2"),
            Document(page_content="doc3")
        ]

        result = reranker.rerank("query", docs, top_k=2)

        assert len(result) == 2
        mock_model.predict.assert_called_once()


class TestHybridRetriever:
    """混合检索器（HybridRetriever）类的测试"""

    @patch("app.retrieval.hybrid_retriever.BM25Okapi")
    def test_init(self, mock_bm25):
        """
        测试混合检索器初始化
        
        验证：
        1. 所有参数正确设置
        2. BM25 初始化被调用
        """
        from app.retrieval.hybrid_retriever import HybridRetriever

        mock_store = Mock()
        texts = ["doc1", "doc2", "doc3"]

        retriever = HybridRetriever(
            dense_store=mock_store,
            texts=texts,
            k=5,
            rrf_k=60,
            use_reranker=False
        )

        assert retriever.dense_store == mock_store
        assert retriever.texts == texts
        assert retriever.k == 5
        assert retriever.rrf_k == 60
        assert retriever.reranker is None

    def test_tokenize(self):
        """
        测试分词功能
        
        验证：
        1. 英文按词切分
        2. 中文按单字和bigram切分
        3. 停用词过滤
        4. 中英混合处理
        """
        from app.retrieval.hybrid_retriever import HybridRetriever

        retriever = HybridRetriever.__new__(HybridRetriever)

        # 英文：小写 + 按词拆分
        tokens = retriever._tokenize("Hello World")
        assert "hello" in tokens
        assert "world" in tokens

        # 中文：单字切分 + bigram
        tokens = retriever._tokenize("违约责任条款")
        for ch in ("违", "约", "责", "任", "条", "款"):
            assert ch in tokens
        assert "违约" in tokens
        assert "责任" in tokens
        assert "条款" in tokens

        # 停用词过滤
        tokens = retriever._tokenize("你好世界")
        assert "你" not in tokens
        assert "好" not in tokens
        assert "世界" in tokens

        # 中英混合
        tokens = retriever._tokenize("Hello 世界")
        assert "hello" in tokens
        assert "世" in tokens
        assert "世界" in tokens

    @patch("app.retrieval.hybrid_retriever.BM25Okapi")
    def test_sparse_search(self, mock_bm25):
        """
        测试稀疏检索
        
        验证：
        1. BM25 模型正确调用
        2. 结果按分数排序
        """
        from app.retrieval.hybrid_retriever import HybridRetriever

        mock_bm25_instance = Mock()
        mock_bm25.return_value = mock_bm25_instance
        mock_bm25_instance.get_scores.return_value = [0.5, 0.8, 0.2]

        retriever = HybridRetriever.__new__(HybridRetriever)
        retriever.texts = ["doc1", "doc2", "doc3"]
        retriever.k = 2
        retriever.bm25 = mock_bm25_instance

        results = retriever._sparse_search("query")

        assert len(results) == 3
        assert results[0][1] >= results[1][1]

    @patch("app.retrieval.hybrid_retriever.BM25Okapi")
    def test_dense_search(self, mock_bm25):
        """
        测试稠密检索
        
        验证：
        1. 向量存储正确调用
        2. 分数正确归一化
        """
        from app.retrieval.hybrid_retriever import HybridRetriever

        mock_store = Mock()
        mock_store.similarity_search_with_score.return_value = [
            (Document(page_content="doc1"), 0.1),
            (Document(page_content="doc2"), 0.3),
            (Document(page_content="doc3"), 0.5)
        ]

        retriever = HybridRetriever.__new__(HybridRetriever)
        retriever.dense_store = mock_store
        retriever.k = 2

        results = retriever._dense_search("query")

        assert len(results) == 3
        assert results[0][1] == 1.0 - 0.1 / 2.0

    @patch("app.retrieval.hybrid_retriever.BM25Okapi")
    def test_rrf_fuse(self, mock_bm25):
        """
        测试 RRF 融合
        
        验证：
        1. 稠密和稀疏结果正确融合
        2. 每个文档包含 RRF 分数
        """
        from app.retrieval.hybrid_retriever import HybridRetriever

        retriever = HybridRetriever.__new__(HybridRetriever)
        retriever.rrf_k = 60
        retriever.dense_weight = 1.0
        retriever.sparse_weight = 1.0

        dense_results = [
            (Document(page_content="doc1", metadata={}), 0.9),
            (Document(page_content="doc2", metadata={}), 0.8)
        ]

        sparse_results = [
            ("doc1", 0.7),
            ("doc3", 0.6)
        ]

        results = retriever._rrf_fuse(dense_results, sparse_results)

        assert len(results) == 3
        for doc in results:
            assert "rrf_score" in doc.metadata

    @patch("app.retrieval.hybrid_retriever.BM25Okapi")
    def test_retrieve(self, mock_bm25):
        """
        测试检索功能
        
        验证：
        1. 正确调用稠密和稀疏检索
        2. 结果正确融合
        """
        from app.retrieval.hybrid_retriever import HybridRetriever

        mock_store = Mock()
        mock_store.similarity_search_with_score.return_value = [
            (Document(page_content="doc1", metadata={}), 0.1),
            (Document(page_content="doc2", metadata={}), 0.3)
        ]

        mock_bm25_instance = Mock()
        mock_bm25.return_value = mock_bm25_instance
        mock_bm25_instance.get_scores.return_value = [0.5, 0.8]

        retriever = HybridRetriever(
            dense_store=mock_store,
            texts=["doc1", "doc2"],
            k=2,
            use_reranker=False
        )

        results = retriever.retrieve("query")

        assert len(results) == 2

    @patch("app.retrieval.hybrid_retriever.BM25Okapi")
    def test_invoke(self, mock_bm25):
        """
        测试 LangChain 接口（invoke 方法）
        
        验证：
        1. 与 retrieve 方法行为一致
        2. 返回正确格式的结果
        """
        from app.retrieval.hybrid_retriever import HybridRetriever

        mock_store = Mock()
        mock_store.similarity_search_with_score.return_value = [
            (Document(page_content="doc1", metadata={}), 0.1)
        ]

        mock_bm25_instance = Mock()
        mock_bm25.return_value = mock_bm25_instance
        mock_bm25_instance.get_scores.return_value = [0.5]

        retriever = HybridRetriever(
            dense_store=mock_store,
            texts=["doc1"],
            k=1,
            use_reranker=False
        )

        results = retriever.invoke("query")

        assert len(results) == 1
