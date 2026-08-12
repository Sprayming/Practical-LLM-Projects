"""
tests.unit 包 —— legal-doc-rag 项目单元测试代码的子包初始化文件。

【测试覆盖范围】
- 本包聚合所有单元测试模块(test_config、test_hybrid_retriever_v3、
  test_memory_manager_fixed、test_bge_m3_sparse、test_api_chat_simple 等)，
  本身不含测试逻辑。

【适用场景】
- 由 pytest 自动识别为单元测试子包，集中存放 app.* 各模块的单元测试。

【依赖】
- 依赖 pytest 及各单元测试模块所引用的 app.* 业务代码。
"""

# Unit tests for Legal-DOC-RAG