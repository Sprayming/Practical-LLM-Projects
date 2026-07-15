# ============================================================
# legal-doc-rag - 框架总览与文件关系图
# 路径基准: legal-doc-rag/app/（代码）, legal-doc-rag/（根目录）
# ============================================================

"""
Part 1: legal-doc-rag 架构总览

┌─────────────────────────────────────────────────────────────────────┐
│  streamlit_app.py (入口)                                            │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │ 记忆系统 (memory/)                                            │   │
│  │  ┌─────────────────┐  ┌────────────┐  ┌────────────────┐   │   │
│  │  │ memory_manager  │→│redis_client│  │  forgetting    │   │   │
│  │  │ (3层:短/中/长)  │  │(TTL过期)   │  │ (艾宾浩斯曲线) │   │   │
│  │  └────────┬────────┘  └────────────┘  └────────────────┘   │   │
│  │           │→ worker/shadow_worker.py (异步持久化)              │   │
│  └───────────┼─────────────────────────────────────────────────┘   │
│              │                                                     │
│  ┌───────────┼─────────────────────────────────────────────────┐   │
│  │ 文档处理 (processing/)                                        │   │
│  │  multimodal_pipeline.py                                       │   │
│  │    ├── pdf_extractor.py  (PyMuPDF 图文提取)                  │   │
│  │    └── ocr_engine.py     (PaddleOCR/Tesseract)              │   │
│  └───────────┼─────────────────────────────────────────────────┘   │
│              │                                                     │
│  ┌───────────┼─────────────────────────────────────────────────┐   │
│  │ 检索 (retrieval/)                                            │   │
│  │  hybrid_retriever.py  (BM25 + Dense + RRF + Cross-Encoder)  │   │
│  │  citation.py          (来源标注)                            │   │
│  │  query_rewriter.py    (LLM 查询改写)                       │   │
│  └───────────┼─────────────────────────────────────────────────┘   │
│              │                                                     │
│  ┌───────────┼─────────────────────────────────────────────────┐   │
│  │ 评估 (evaluation/)                                           │   │
│  │  evaluator.py  →  RAGAS (Faithfulness/Relevancy/Recall)   │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  独立能力模块:                                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐    │
│  │ worker/      │  │ tenant/      │  │ observability/       │    │
│  │ shadow_worker│  │ tenant_mgr   │  │ tracker.py           │    │
│  │ (异步任务)   │  │ (多租户隔离)  │  │ (全链路追踪)         │    │
│  └──────────────┘  └──────────────┘  └──────────────────────┘    │
└─────────────────────────────────────────────────────────────────────┘

Part 2: 文件关系图 (import 链)

┌──────────────────────────────────────────────────────────────┐
│  streamlit_app.py                                            │
│  └── memory/memory_manager.py                                │
│       ├── memory/redis_client.py    (Redis 连接)              │
│       ├── memory/forgetting.py      (遗忘算法)                │
│       └── worker/shadow_worker.py   (异步任务)                │
│                                                              │
│  multimodal_pipeline.py (processing/)                        │
│  ├── processing/pdf_extractor.py    (PyMuPDF 提取)            │
│  └── processing/ocr_engine.py       (OCR 识别)                │
│                                                              │
│  retrieval/ (独立模块, 无交叉引用)                              │
│  ├── hybrid_retriever.py   (混合检索)                         │
│  ├── citation.py           (来源标注)                         │
│  └── query_rewriter.py     (查询改写)                         │
│                                                              │
│  evaluation/ (独立使用 RAGAS)                                  │
│  └── evaluator.py                                             │
│                                                              │
│  完全独立模块:                                                │
│  ├── worker/shadow_worker.py         (异步队列)               │
│  ├── tenant/tenant_manager.py       (多租户)                  │
│  └── observability/tracker.py        (全链路追踪)             │
└──────────────────────────────────────────────────────────────┘

Part 3: 模块详解

1. memory/memory_manager.py  ──── 三层记忆系统
   为什么?     对话需要记住上下文, 单一存储不够
   解决了?     Redis短期 + ChromaDB长期 + 异步持久化 + 遗忘曲线
   如果删掉?   每次对话都是独立的, 无法多轮交互

2. memory/redis_client.py  ──── Redis 连接管理
   为什么?     短期/中期记忆需要快速读写和TTL过期
   解决了?     Redis自动过期 + 内存回退
   如果删掉?   只能用慢速的ChromaDB做所有记忆

3. memory/forgetting.py  ──── 遗忘机制
   为什么?     记忆无限堆积会影响检索质量
   解决了?     艾宾浩斯曲线评分: 近因性50%+频率30%+重要性20%
   如果删掉?   旧记忆和重要记忆无法区分

4. processing/pdf_extractor.py  ──── PDF图文提取
   为什么?     PDF含图片和表格, 纯文本提取会丢失信息
   解决了?     PyMuPDF提取文本+图片, 支持多页/多图
   如果删掉?   只能处理纯文本文件

5. processing/ocr_engine.py  ──── OCR引擎
   为什么?     图片中的文字需要识别才能被检索
   解决了?     自动检测PaddleOCR/Tesseract, 支持中文
   如果删掉?   图片内容无法被索引

6. processing/multimodal_pipeline.py  ──── 多模态管线
   为什么?     需要串联 图文提取 → OCR → 合并 → 分块
   解决了?     一步完成多模态文档处理
   如果删掉?   需要手动调用多个步骤

7. retrieval/hybrid_retriever.py  ──── 混合检索器
   为什么?     纯稠密向量对同义词/专有名词召回不够
   解决了?     BM25+Dense双路 + RRF融合 + Cross-Encoder精排
   如果删掉?   Top-N命中率下降25%+

8. retrieval/query_rewriter.py  ──── 查询改写器
   为什么?     用户问得模糊时检索效果差
   解决了?     LLM扩展同义词/分解复合问题, 多路检索
   如果删掉?   "合同怎么签"可能搜不到"劳动合同签订流程"

9. retrieval/citation.py  ──── 来源标注
   为什么?     回答需要可追溯, 建立信任
   解决了?     追踪chunk来源, 生成引用列表
   如果删掉?   回答不可验证

10. evaluation/evaluator.py  ──── RAGAS评估
    为什么?     需要量化评估检索和生成质量
    解决了?     Faithfulness/Relevancy/Recall 三维度打分
    如果删掉?   无法衡量优化效果

11. worker/shadow_worker.py  ──── 异步影子Worker
    为什么?     记忆整理/模型调用等耗时操作不应阻塞对话
    解决了?     优先级任务队列 + 多线程 + 自动重试
    如果删掉?   记忆整理等操作会卡住UI

12. tenant/tenant_manager.py  ──── 多租户隔离
    为什么?     多个用户/团队使用同一系统, 数据需隔离
    解决了?     独立Collection + 命名空间
    如果删掉?   所有用户共享同一份数据

13. observability/tracker.py  ──── 全链路追踪
    为什么?     出问题需要定位是哪个环节
    解决了?     TraceSpan记录每阶段耗时/Token/异常
    如果删掉?   出问题无法排查

Part 4: 能力总结

模块              能力                      简历表述
───────────────────────────────────────────────────────────
memory/           三层记忆 + Redis + 遗忘     "通过Redis分层管理长短期上下文记忆"
processing/       多模态PDF处理 + OCR          "集成OCR和Vision LLM实现多模态文档解析"
retrieval/        混合检索 + 重排序 + 改写    "BM25+Dense双路 + RRF融合 + Cross-Encoder"
evaluation/       RAGAS评估                  "基于RAGAS建立三维度打分机制"
worker/           异步Worker                 "通过异步多线程持久化记忆"
tenant/           多租户隔离                  "实现租户级数据隔离"
observability/    全链路追踪                  "全链路可观测性"
"""
