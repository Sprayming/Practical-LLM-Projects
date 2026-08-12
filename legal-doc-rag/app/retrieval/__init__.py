"""
检索模块（retrieval）—— legal-doc-rag RAG 系统的召回与融合层。

【作用与功能】
本包封装了从多种存储/索引中召回相关法律文档片段，并融合排序的核心能力。
它向上层（索引构建、问答流水线）提供统一的检索接口，向下整合稠密向量、
稀疏 BM25、Elasticsearch 全文以及 BGE-M3 学习稀疏等召回通道。

【主要组成】
- `HybridRetriever`：混合检索器（稠密 + 稀疏 + ES + RRF 融合 + 重排序）
- `BGEM3Embedder`：BGE-M3 稠密/稀疏嵌入器
- `embedder_factory.create_embedder`：按配置创建嵌入器
- `sparse_store`：BGE-M3 稀疏向量持久化
- `elasticsearch_client`：ES 全文检索客户端
- `cache.QueryCache`：查询答案缓存
- `citation.CitationTracker`：引用来源追踪
- `query_rewriter.QueryRewriter`：查询改写

【适用场景】
- 场景1：文档入库时为 chunk 生成并保存稠密/稀疏向量
- 场景2：用户提问时由 HybridRetriever 召回并融合 Top-K 片段

【依赖关系】
- 上游调用方：索引构建脚本、RAG 问答流水线
- 下游依赖：Chroma（稠密）、FlagEmbedding（BGE-M3）、Elasticsearch、cache/sparse 存储
"""
