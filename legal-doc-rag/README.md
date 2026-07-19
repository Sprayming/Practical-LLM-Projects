# Legal Document RAG

## Overview

基于 Streamlit 的法律文书智能问答系统。上传 PDF 合同、法规、法律文件，用自然语言提问，系统自动检索相关条款并生成带引用的回答。

## 架构总览

```
streamlit_app.py (唯一入口, ~220 行)
  |
  +-- memory/memory_manager.py    3 层记忆 (短/中/长期)
  |     +-- redis_client.py        Redis 连接 + TTL 过期 + 内存回退
  |     +-- forgetting.py           艾宾浩斯遗忘曲线
  |     +-- shadow_worker.py        异步后台线程池
  |
  +-- processing/multimodal_pipeline.py  PDF 图文提取
  |     +-- pdf_extractor.py        PyMuPDF 图文提取
  |     +-- ocr_engine.py           OCR (PaddleOCR / Tesseract)
  |
  +-- retrieval/
  |     +-- hybrid_retriever.py     BM25 + Dense + RRF + Cross-Encoder
  |     +-- query_rewriter.py       LLM 查询改写/扩展
  |     +-- citation.py             来源引用追踪
  |
  +-- evaluation/                   (离线评测, 不在在线流中)
  |     +-- evaluator.py            RAGAS 三维度打分
  |     +-- runner.py               批量评测 + Golden Test Set
  |
  +-- tenant/tenant_manager.py     多租户数据隔离
  |
  +-- observability/tracker.py     全链路追踪 (耗时, Token)
  |
  +-- worker/shadow_worker.py      共享异步线程池
```

## 数据流 (在线)

```
用户输入
  |
  v
MultimodalPipeline.process(PDF path)
  |  从 PDF 提取文字, 对图片运行 OCR,
  |  生成图片描述, 合并到文本分块
  v
HybridRetriever(dense_store, texts) -> retriever
  |
  v  (每次用户提问)
QueryRewriter.rewrite(query)
  |  LLM 改写/扩展用户查询
  v
HybridRetriever.invoke(query)
  |  BM25 + 稠密向量 + RRF 融合 -> documents[]
  v
CitationTracker.add_sources(docs)
  |  标注 [source:N] 引用
  v
MemorySystem.get_context(query)
  |  1. 长期记忆: Chroma + 遗忘过滤
  |  2. 中期记忆: Redis 摘要
  |  3. 短期记忆: 最近 4 轮原话
  v
LLM (DeepSeek)
  |  Prompt = system + context + citations + memory + question
  v
MemorySystem.add(assistant, answer)
MemorySystem.extract_entities() -> ShadowWorker 异步
  v
TraceContext -> get_trace_store().save()
```

## 三层记忆系统

```
短期记忆 (最近 6 轮原文, ~600 token)
  内存 + Redis List (TTL 2h)
  维持当前对话连贯性
  |
  v  (超过 6 轮时触发整理)
中期记忆 (LLM 压缩摘要, ~200 token)
  内存 + Redis String (TTL 24h)
  增量合并: 旧摘要 + 新对话 -> LLM -> 合并摘要
  |
  v  (ShadowWorker 异步执行)
长期记忆 (ChromaDB 向量库, 永久)
  遗忘曲线: score = 0.5*近因 + 0.3*频率 + 0.2*重要性
  访问即激活: 检索时异步递增 access_count
  |
  v
实体画像 (异步提取)
  LLM 从每轮对话提取结构化 JSON 实体
  存入长期记忆的 type=entity 文档
```

## Token 预算分配

| 层级 | 预算 | 说明 |
|------|------|------|
| System Prompt | ~100 | 固定不变 |
| 短期记忆 (6轮) | ~600 | 超出丢弃最旧 |
| 实体画像 | ~100 | JSON 结构化, 始终加载 |
| 长期记忆 (检索) | ~500 | Top-3, 遗忘过滤 |
| 检索文档 | ~2000 | Top-5, 去重 |
| 用户输入 | <500 | 前端限制 |
| 总计 | ~3800 | 预留回答空间 |

## 快速开始

```bash
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple/
cp .env.example .env
# 编辑 .env: 填入 LLM_API_KEY
cd legal-doc-rag
streamlit run app/streamlit_app.py
```

## 技术栈

| 组件 | 选型 | 文件 |
|------|------|------|
| 前端 UI | Streamlit | streamlit_app.py |
| 嵌入模型 | text2vec-base-chinese | streamlit_app.py |
| 文档向量库 | ChromaDB | streamlit_app.py |
| 记忆向量库 | ChromaDB | memory/memory_manager.py |
| 缓存层 | Redis (可选, 有回退) | memory/redis_client.py |
| LLM | DeepSeek API | streamlit_app.py |
| PDF 解析 | PyMuPDF + MultimodalPipeline | processing/ |
| 混合检索 | BM25 + Dense + RRF | retrieval/hybrid_retriever.py |
| 查询改写 | LLM (DeepSeek) | retrieval/query_rewriter.py |
| 引用标注 | Source tracking | retrieval/citation.py |
| 异步 Worker | 守护线程池 | worker/shadow_worker.py |
| 全链路追踪 | 内存存储 | observability/tracker.py |

## 项目状态

- [x] 基础 RAG 问答 (文档检索 + 引用溯源)
- [x] 三层记忆系统 (短/中/长 + 实体画像)
- [x] 实体提取 (异步 LLM -> 结构化 JSON)
- [x] Token 统计与预算控制
- [x] 混合检索器 (BM25 + Dense + RRF)
- [x] 查询改写 (LLM 扩展)
- [x] 引用追踪 (来源标注)
- [x] 多模态管线 (PDF 文字 + 图片 + OCR)
- [x] 异步 Shadow Worker (后台记忆整理)
- [x] 遗忘机制 (艾宾浩斯曲线)
- [x] Redis 容错 (内存回退)
- [x] 用户画像 ProfileStore (JSON, 置信度合并)
- [x] 多租户隔离 (Sidebar Tenant ID, 独立记忆/画像)
- [x] RAGAS 离线评测 (6 题 Golden Test Set)
  - Faithfulness: 0.38 / AnswerRelevancy: 0.96
  - ContextPrecision: 1.0 / ContextRecall: 1.0

## 更新日志

### 2026-07-19: RAGAS 评测跑通 + ProfileStore + 多租户
- RAGAS 评测跑通真实分数 (豆包 API + 豆包 embedding)
- 新增 ProfileStore: 用户画像独立存储 (置信度加权合并)
- 多租户隔离: Sidebar Tenant ID, 隔离记忆/N/画像
- 修复 EvaluationResult 访问方式 (r.scores 而非 dict)

### 2026-07-19: 接通全部闲置模块
- MultimodalPipeline: 替换 PyPDF2 + splitter (图文+OCR)
- HybridRetriever: 替换直接 Chroma retriever (BM25+Dense+RRF)
- QueryRewriter: 检索前 LLM 改写查询
- CitationTracker: 检索结果来源标注
- TraceContext: 全链路耗时 + Token 追踪
- 移除 PyPDF2 和 RecursiveCharacterTextSplitter import

### 2026-07-19: 5 项生产级改进 (memory_manager.py)
1. clear_session: 修复 Redis 僵尸数据 (先清数据再重置 session_id)
2. 异步访问计数: 检索时反遗忘 (ShadowWorker 批量更新)
3. 实体提取: 实现 _do_extract_entity (原为 pass)
4. 增量摘要合并: 旧摘要+新对话 -> LLM -> 合并
5. Redis 容灾恢复: __init__ 末尾调用 _restore_from_redis()

### 2026-07-18: 消除 Monkey Patching
- 删除 original_xxx / patched_xxx / 模块末尾赋值
- ForgettingMechanism 和 ShadowWorker 直接内建在类方法中
- 修复 extract_entities stub, 添加 memory_llm 回调
- 删除 .orig 备份文件

## 面试常见问题

### Q1: 为什么用 BM25 + Dense + RRF, 不用纯语义检索?
BM25 精确匹配关键词 (条款编号、法律术语). Dense 向量捕捉同义词和意译. RRF 无参数融合两路排序. 纯语义检索漏精确匹配, 纯 BM25 漏语义匹配.

### Q2: Cross-Encoder 和 Bi-Encoder 的区别?
Bi-Encoder 分别编码 query 和 doc, 速度快但精度低. Cross-Encoder 将 query+doc 配对输入, 精度高但慢. 生产: Bi-Encoder 初筛 (top-100), Cross-Encoder 精排 (top-30).

### Q3: 分块大小为什么选 500?
太小 (128) 语义不完整. 太大 (1024+) 含多个主题检索不准. 500 是经验值. Overlap 50 防止关键句被切在边界.

### Q4: RAGAS 四个指标怎么算?
1. Faithfulness: 将回答拆成 claim, 逐条判断是否被上下文支持. 2. AnswerRelevancy: 从回答反向生成问题, 与原问题的相似度. 3. ContextPrecision: 检索结果中相关 chunk 的比例. 4. ContextRecall: ground truth claims 是否出现在检索结果中.

### Q5: 多模态 PDF 解析怎么做的?
PyMuPDF 提取 PDF 中的图片. Vision LLM (通过 API) 对图片生成描述. OCR 提取图片中文字. 描述+OCR 文字合并到该页的文本 chunk 中. 实现搜文字出图.

### Q6: 记忆系统怎么设计的?
三层: 短期(最近 N 轮原文, Redis List TTL 2h), 中期(LLM 摘要, Redis String TTL 24h), 长期(ChromaDB 向量库, 永久). 后台 Worker 异步整理 短->中->长. 遗忘机制基于艾宾浩斯曲线自动过滤低分记忆.

### Q7: 最大的技术挑战是什么?
Golden Test Set 的设计. 不同人写的 ground truth 标准不一致导致 RAGAS 评分波动. 统一模板: question / ground_truth / source_doc / difficulty. 评估体系稳定后才开始做优化.

### Q8: 为什么不用 LangChain/LlamaIndex 端到端?
它们解决的是搭积木的问题 — 提供现成的组件（ChromaDB 封装、Prompt 模板、文档加载器）, 让你快速拼出一条 RAG pipeline。但真正产生价值的地方是关键节点上的定制。

1. **检索策略**: LangChain 的 as_retriever() 只调 ChromaDB similarity_search, 一条腿走路。我们手写了 BM25 + 稠密向量 + RRF 融合 + Cross-Encoder 精排。法律检索同时需要精确匹配条款编号和语义匹配同义表述。

2. **记忆系统**: LangChain 自带的 ConversationBufferMemory 只是把所有历史拼进 prompt, 不做分层、不做摘要压缩、不做遗忘衰减。我们手写了三层记忆（短期原文→中期 LLM 摘要→长期向量 + 遗忘曲线）。

3. **评测体系**: LangChain 不负责评测。RAGAS 框架能跑分, 但 Golden Test Set（题、答案、context）全是业务层的功夫。

**结论**: LangChain/LlamaIndex 当工具用, 不当框架用。省掉连 ChromaDB 怎么写这类体力活, 但核心问题（检索不准、记忆不强、怎么评估）框架不管, 得自己写。

## 学习建议

1. 先看 streamlit_app.py 理解完整流程 (2 小时)
2. 研究 memory/memory_manager.py 记忆系统 (3 小时)
3. 研究 retrieval/hybrid_retriever.py 混合检索 (2 小时)
4. 准备面试追问 (2 小时)
5. 不看代码复述项目 (1 小时)