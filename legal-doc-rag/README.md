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


## 变更记录与面试角度

### 1. HybridRetriever (retrieval/hybrid_retriever.py)
改动: BM25 + Dense 双路检索 + RRF 融合 + Cross-Encoder 重排序
原因: 纯稠密对同义词/专有名词召回不够, BM25 做关键词补充; RRF 解决两路分数尺度不一致
面试可能问:
- RRF k 值为什么选 60? 答: k 控制排名敏感度, 60 是论文推荐默认值
- Cross-Encoder vs Bi-Encoder? 答: Bi-Encoder 分别编码(快), Cross-Encoder 拼一起输入(准), 实践中 Bi-Encoder 做召回, Cross-Encoder 做精排

### 2. QueryRewriter (retrieval/query_rewriter.py)
改动: LLM 查询改写, 同义词扩展 + 复合问题分解 + 规则兜底
原因: 用户问得模糊时检索效果差
面试可能问: 改写失败怎么办? 答: LLM 失败时返回原查询, 规则级扩展兜底

### 3. CitationTracker (retrieval/citation.py)
改动: 检索来源追踪 + 自动生成引用列表
原因: 回答需要可追溯, 建立用户信任
面试可能问: 引用怎么实现的? 答: 检索时记录每个 chunk 的源信息, 拼接上下文时附带 [来源: filename] 标记

### 4. MemorySystem + RedisClient (memory/)
改动: 重构三层记忆(短/中/长), 集成 Redis TTL 过期 + 内存回退
原因: 单一存储不够; Redis 快速读写 + 自动过期适合短/中期记忆
面试可能问:
- Redis 不可用时? 答: 自动回退内存存储, 不阻塞对话
- TTL 怎么设? 答: 短期 2h, 中期 24h, 环境变量配置
- 为什么用 Redis? 答: 支持 TTL、List/String 结构适合记忆场景、低延迟

### 5. ForgettingMechanism (memory/forgetting.py)
改动: 艾宾浩斯遗忘曲线记忆衰减 + 自动清理
原因: 记忆无限堆积影响检索质量
面试可能问: 算法公式? 答: 分数=0.5x近因性+0.3x频率+0.2x重要性, 近因性=exp(-小时数/168)

### 6. MultimodalPipeline + OCREngine (processing/)
改动: PyMuPDF 图文提取 + OCR(PaddleOCR/Tesseract) + 合并分块
原因: PDF 含图片和表格, 纯文本提取会丢失信息
面试可能问: PPT/PDF 图怎么处理? 答: 遍历页面提取图片, OCR 识别后缝合进文本 Chunk

### 7. VisionCaptioner (ingestion/vision_caption.py)
改动: Vision LLM 图片标注, 生成 Caption 缝合进 Chunk
原因: 图片无法直接被检索, Caption 实现"搜文字出图"
面试可能问: 延迟怎么处理? 答: 异步调用不阻塞; 失败时回退 OCR 文字

### 8. RAGASEvaluator + RegressionRunner (evaluation/)
改动: RAGAS 三维度(Faithfulness/Relevancy/Recall) + 31 道 Golden Test Set + 回归历史追踪
原因: 量化评估检索和生成质量, 确保优化不退化
面试可能问:
- 三维度怎么算? 答: Faithfulness 拆 claim 判断是否被支持; Relevancy 反向生成问题算相似度; Recall 判断 ground truth 是否出现在检索结果中
- 测试集怎么设计的? 答: 31 道题覆盖 10 类法律场景, 每道含 question/ground_truth/difficulty

### 9. ShadowWorker (worker/shadow_worker.py)
改动: 异步影子 Worker, 优先级队列 + 多线程 + 自动重试
原因: 记忆整理等耗时操作不阻塞主流程
面试可能问: Worker 挂了? 答: 任务标记 failed, 可配置重试; 主进程管理 Worker 自动恢复

### 10. TenantManager (tenant/tenant_manager.py)
改动: 多租户隔离, 独立 namespace + ChromaDB Collection + Redis Key 前缀
原因: 多用户数据需隔离
面试可能问: 怎么隔离? 答: collection_name = tenant:{id}:knowledge, redis_prefix = tenant:{id}:memory

### 11. TraceContext (observability/tracker.py)
改动: 全链路追踪, TraceSpan 记录每阶段耗时/Token/异常
原因: 出问题需要定位环节
面试可能问: 影响性能? 答: 不限, 只是计时计数, 内存保留最近 1000 条

### 12. Docker 容器化 (Dockerfile + docker-compose.yml)
改动: Docker 部署, 编排 app(8501) + redis(6379) 两个服务
原因: 生产环境部署需要容器化, 确保环境一致性
面试可能问:
- 镜像多大? 答: 约 2-3GB, 含 Python 依赖和模型文件
- Redis 挂了? 答: 无法使用记忆功能, 基础检索问答仍可用(回退内存)

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
它们解决的是搭积木的问题 — 提供现成的组件（ChromaDB 封装、Prompt 模板、文档加载器），让你快速拼出一条 RAG pipeline。但真正产生价值的地方是关键节点上的定制。

1. **检索策略**: LangChain 的 as_retriever() 只调 ChromaDB similarity_search，一条腿走路。我们手写了 BM25 + 稠密向量 + RRF 融合 + Cross-Encoder 精排。法律检索同时需要精确匹配条款编号和语义匹配同义表述。

2. **记忆系统**: LangChain 自带的 ConversationBufferMemory 只是把所有历史拼进 prompt，不做分层、不做摘要压缩、不做遗忘衰减。我们手写了三层记忆（短期原文→中期 LLM 摘要→长期向量 + 遗忘曲线）。

3. **评测体系**: LangChain 不负责评测。RAGAS 框架能跑分，但 Golden Test Set（题、答案、context）全是业务层的功夫。

**结论**: LangChain/LlamaIndex 当工具用，不当框架用。省掉连 ChromaDB 怎么写这类体力活，但核心问题（检索不准、记忆不强、怎么评估）框架不管，得自己写。

### Q9: embedding 模型怎么选？为什么从 text2vec 换成了豆包？
三种方式，改一行代码就能切：

| 方式 | 示例 | 费用 | 备注 |
|------|------|------|------|
| 本地模型 | text2vec-base-chinese / BGE | 免费 | 需下载，离线可用 |
| 在线 API | 豆包 / OpenAI | 按量付费 | 即开即用，无网络问题 |
| 自定义 | DirectEmbed 包装任意 API | 视 API 而定 | 接口统一，可灵活切换 |

实际项目中的选型原则：

1. **原型期**: 在线 API 最快跑通。我们最初用 text2vec 本地模型，但服务器 SSL 证书问题连不上 huggingface，换成了豆包 embedding API。这是生产中的常见策略降级。
2. **上线后**: 如果 QPS 高，切到本地 BGE 模型降本。如果 query 主要是法律条款精确匹配，BGE 可能比通用 embedding 更合适。
3. **维度不是越高越好**: 2560 维对比 768 维，对单文档问答场景没有肉眼可见的提升，但内存占用高 3 倍。对 10 万级以上的知识库有明显成本差异。
4. **很少自己训**: 除非有几十万条标注好的三元组（问题，相关文档，不相关文档），否则直接训不如拿 BGE 微调。

**面试答案**: embedding 选型是个 trade-off — 要离线/在线、免费/付费、通用/领域、高维/低维。关键是你做过取舍，不是背参数表。
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
## Docker 部署

### 文件说明
- Dockerfile: python:3.12-slim, 预装依赖 + 可选预下载嵌入模型
- docker-compose.yml: 编排 app + redis 两个服务
- .dockerignore: 排除缓存、本地数据

### 使用
```bash
cp .env.example .env   # 填入 LLM_API_KEY
docker compose up -d   # 启动
docker compose logs -f # 日志
docker compose down    # 停止
```

### 服务架构
```
浏览器 :8501 → App(Streamlit) → redis://redis:6379
```

### 数据卷
- model_cache: 嵌入模型缓存(避免每次启动下载)
- memory_db: ChromaDB 持久化
- redis_data: Redis AOF 持久化

### 16. 流式输出 (streamlit_app.py)
改动: DeepSeek API 改为 SSE 流式输出, 逐字显示回答
原因: 用户体验提升, 感知延迟大幅降低
面试: 流式和普通请求区别? 答: stream=True 逐行解析, 边生成边显示

### 17. 用户认证 (streamlit_app.py)
改动: 新增可选密码认证, 通过 APP_PASSWORD 开启
原因: 生产环境需要基本访问控制
面试: 为什么不用 JWT? 答: Streamlit 单页应用, 密码足够

### 18. 用户反馈 (streamlit_app.py)
改动: 每条回答后增加有用/没用按钮, 记录到 feedback_log.json
原因: 收集反馈持续改进 RAG








### 19. CI/CD (GitHub Actions)
改动: 新增 GitHub Actions CI 工作流
原因: 自动语法检查 + Golden Test Set 验证
面试可能问: CI 跑什么检查? 答: 语法检查和测试集验证

### 20. 健康检查 (healthcheck.py + docker-compose.yml)
改动: 新增 Docker 健康检查
原因: 容器编排需要健康检查
面试可能问: 健康检查怎么实现? 答: TCP 连接检测 port 8501


### 21. 结构化日志 (app/observability/structured_logger.py)
改动: 新增 JSON 结构化日志模块, 集成到主应用
原因: 生产环境需要可搜索、可聚合的日志, RotatingFileHandler 自动轮转
文件:
  - app/observability/structured_logger.py: 日志类, JSON 格式, 支持 RotatingFileHandler
  - streamlit_app.py: 在 query 流程中调用 logger.info()
面试可能问: 为什么不用 print? 答: print 无法按照级别过滤, 不支持结构化输出, RotatingFileHandler 防止日志撑爆磁盘

### 22. 对话持久化 (app/memory/conversation_store.py)
改动: 新增对话历史持久化到文件, 每次问答后自动保存
原因: 用户对话记录需要持久化保存, 支持断点续聊和历史追溯
文件:
  - app/memory/conversation_store.py: 以 JSON 格式保存对话到 conversations/ 目录
  - streamlit_app.py: 在问答流程结束后调用 conversation_store.save()
面试可能问: 为什么不用数据库? 答: 文件存储对单机部署足够, JSON 便于人工查看和调试

### 23. 查询缓存 (app/retrieval/cache.py)
改动: 新增查询结果缓存, 24h TTL, MD5 作为 key
原因: 相同问题的重复查询直接返回缓存结果, 减少 API 调用次数和延迟
文件:
  - app/retrieval/cache.py: 文件级缓存, MD5 key, 24h 过期, 自动清理
  - streamlit_app.py: 在查询缓存 hit 时直接返回, miss 时请求 API 后写入缓存
面试可能问: 缓存过期策略? 答: 24h TTL, 读时惰性删除, 可扩展 LRU


### 24. 前端界面重构 (streamlit_app.py)
改动: 全面重写 UI 界面，注入自定义 CSS 主题
原因: 原版 Streamlit 默认样式较为简陋，需要提升用户体验和专业感
改动内容:
  - 注入自定义 CSS: 深蓝导航主题, 圆角卡片, 渐变侧边栏
  - 侧边栏重构: 品牌区域 + 分类卡片 + 会话统计 + 版本水印
  - 主区域优化: 自定义页面标题 + 欢迎引导卡片 + 操作步骤提示
  - 消息区域美化: 用户消息蓝底高亮, AI 消息白底卡片, 统一圆角阴影
  - 空状态优化: 引导用户上传文档的三步指引卡片
面试可能问: Streamlit 怎么自定义样式? 答: st.markdown() 注入 CSS, 用 unsafe_allow_html=True
面试可能问: 为什么不用前端框架? 答: Streamlit 优势在于快速构建数据应用, 自定义 CSS 足以达到专业效果
