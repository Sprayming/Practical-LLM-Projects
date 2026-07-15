# ============================================================
# RAG 智能知识检索系统 - readme.py
# 正确的框架总览 + 文件关系图
# ============================================================

### PART 1: rag-project 架构总览

序列流程：

┌─────────────────────────────────────────────────────────────────────────────────────────────────┐
│  摘录管线 (Ingestion Pipeline)                │
│                                                    │
│  Upload(PDF/DOCX/TXT/图片)                         │
│    ↓                                                  │
│  documents.py [API]                                   │
│    ↓                                                  │
│  pipeline.py [编排]                                    │
│    │── loader.py → 解析文件为纯文本         │
│    │── vision_caption.py → Vision LLM 描述图片  │
│    │── chunker.py → 切分为 Chunk (512/128)     │
│    │── embedder.py → 转向量                  │
│    └── vector_store.py → 存入 ChromaDB          │
│                                                    │
│  检索问答管线 (Retrieval Pipeline)               │
│                                                    │
│  User Query                                        │
│    ↓                                                  │
│  chat.py [API]                                       │
│    │── retriever.py (基础) 或 hybrid_retriever.py (混合)  │
│    │     │── embedder.py → query 转向量         │
│    │     ── vector_store.py → ChromaDB 检索     │
│    │     ── hybrid 额外: BM25 + RRF + Cross-Encoder   │
│    │── citation.py → 追踪引用来源            │
│    │── llm.py → 生成回答 (DeepSeek)           │
│    │     └── prompt_templates.py → 提示词模板  │
│    ↓                                                  │
│  Answer + Citations                                   │
│                                                    │
│  评估体系 (Evaluation)                           │
│  evaluation/runner.py → metrics.py → RAGAS (独立运行)  │
│  tests/golden_test_set.json (31题)                    │
└─────────────────────────────────────────────────────────────────────────────────────────────────┘

### PART 2: 文件关系图

┌─────────────────────────────────────────────────────────────────────────────────┐
│  import <--方向                                      │
│                                                    │
│  main.py                                            │
│    ├─── api/chat.py                                     │
│    │     ├─── models.py (数据模型)                  │
│    │     ├─── retrieval/retriever.py (或 hybrid_retriever)   │
│    │     │     ├─── retrieval/embedder.py                │
│    │     │     └─── retrieval/vector_store.py              │
│    │     │     ─── retrieval/citation.py (引用源)       │
│    │     └─── generation/llm.py                             │
│    │           ├─── generation/prompt_templates.py           │
│    │           └─── config.py                              │
│    ├─── api/documents.py                                  │
│    │     ├─── config.py                                 │
│    │     ├─── models.py                                 │
│    │     └─── ingestion/pipeline.py                       │
│    │           ├─── ingestion/loader.py                    │
│    │           ├─── ingestion/vision_caption.py             │
│    │           ├─── ingestion/chunker.py                    │
│    │           ├─── retrieval/embedder.py                  │
│    │           └─── retrieval/vector_store.py                │
│    ─── evaluation/runner.py (独立运行)                    │
│         └─── evaluation/metrics.py (调用 RAGAS)              │
│                                                    │
│  独立文件:                                   │
│  - ingestion/chunker.py (只被 pipeline import)            │
│  - retrieval/hybrid_retriever.py (可替代 retriever)          │
│  - ingestion/vision_caption.py (被 pipeline可选调用)       │
│  - tests/golden_test_set.json (被 runner加载)               │
└─────────────────────────────────────────────────────────────────────────────────────────────────┘