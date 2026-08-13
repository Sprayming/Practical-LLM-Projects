"""
app.retrieval —— 检索与融合子包（包标识文件）

【作用与功能】
封装从多种存储/索引中召回相关法律文档片段并融合排序的核心能力，向上层提供统一检索接口，
向下整合稠密向量、稀疏 BM25、Elasticsearch 全文以及 BGE-M3 学习稀疏等召回通道。

【实现方式】
本文件仅作为包标识，不承载运行逻辑。具体能力由子模块提供：
- `HybridRetriever`:混合检索器（稠密 + 稀疏 + ES + RRF 融合 + 重排序）
- `BGEM3Embedder` / `embedder_factory`:BGE-M3 稠密/稀疏嵌入与创建工厂
- `sparse_store`:BGE-M3 稀疏向量持久化
- `elasticsearch_client`:ES 全文检索客户端
- `cache.QueryCache`:查询答案缓存
- `citation.CitationTracker`:引用来源追踪
- `query_rewriter.QueryRewriter`:查询改写

【整体作用】
文档入库时为 chunk 生成并保存向量，用户提问时由 HybridRetriever 召回并融合 Top-K 片段，
是 RAG 问答质量的召回基础。
"""
