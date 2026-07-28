# Legal Document RAG





## Overview





基于 Streamlit 的法律文书智能问答系统。上传 PDF 合同、法规、法律文件，用自然语言提问，系统自动检索相关条款并生成带引用的回答





## 架构总览





```


streamlit_app.py (唯一入口, ~220 


  |


  +-- memory/memory_manager.py    3 层记忆(及长期)


  |     +-- redis_client.py        Redis 连接 + TTL 过期 + 内存回退


  |     +-- forgetting.py           艾宾浩斯遗忘曲线


  |     +-- shadow_worker.py        异步后台线程


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


  |     +-- evaluator.py            RAGAS 三维度打


  |     +-- runner.py               批量评测 + Golden Test Set


  |


  +-- tenant/tenant_manager.py     多租户数据隔


  |


  +-- observability/tracker.py     全链路追(耗时, Token)


  |


  +-- worker/shadow_worker.py      共享异步线程


```





## 数据(在线)





```


用户输入


  |


  v


MultimodalPipeline.process(PDF path)


  |  PDF 提取文字, 对图片运OCR,


  |  生成图片描述, 合并到文本分


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


  |  3. 短期记忆: 最4 轮原


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


短期记忆 (最6 轮原 ~600 token)


  内存 + Redis List (TTL 2h)


  维持当前对话连贯


  |


  v  (超过 6 轮时触发整理)


中期记忆 (LLM 压缩摘要, ~200 token)


  内存 + Redis String (TTL 24h)


  增量合并: 旧摘+ 新对-> LLM -> 合并摘要


  |


  v  (ShadowWorker 异步执行)


长期记忆 (ChromaDB 向量 永久)


  遗忘曲线: score = 0.5*近因 + 0.3*频率 + 0.2*重要


  访问即激 检索时异步递增 access_count


  |


  v


实体画像 (异步提取)


  LLM 从每轮对话提取结构化 JSON 实体


  存入长期记忆type=entity 文档


```





## Token 预算分配





| 层级 | 预算 | 说明 |


|------|------|------|


| System Prompt | ~100 | 固定不变 |


| 短期记忆 (6 | ~600 | 超出丢弃最|


| 实体画像 | ~100 | JSON 结构 始终加载 |


| 长期记忆 (检 | ~500 | Top-3, 遗忘过滤 |


| 检索文| ~2000 | Top-5, 去重 |


| 用户输入 | <500 | 前端限制 |


| 总计 | ~3800 | 预留回答空间 |





## 快速开





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


| 文档向量| ChromaDB | streamlit_app.py |


| 记忆向量| ChromaDB | memory/memory_manager.py |


| 缓存| Redis (可 有回退) | memory/redis_client.py |


| LLM | DeepSeek API | streamlit_app.py |


| PDF 解析 | PyMuPDF + MultimodalPipeline | processing/ |


| 混合检| BM25 + Dense + RRF | retrieval/hybrid_retriever.py |


| 查询改写 | LLM (DeepSeek) | retrieval/query_rewriter.py |


| 引用标注 | Source tracking | retrieval/citation.py |


| 异步 Worker | 守护线程| worker/shadow_worker.py |


| 全链路追| 内存存储 | observability/tracker.py |





## 项目状





- [x] 基础 RAG 问答 (文档检+ 引用溯源)


- [x] 三层记忆系统 (+ 实体画像)


- [x] 实体提取 (异步 LLM -> 结构JSON)


- [x] Token 统计与预算控


- [x] 混合检索器 (BM25 + Dense + RRF)


- [x] 查询改写 (LLM 扩展)


- [x] 引用追踪 (来源标注)


- [x] 多模态管(PDF 文字 + 图片 + OCR)


- [x] 异步 Shadow Worker (后台记忆整理)


- [x] 遗忘机制 (艾宾浩斯曲线)


- [x] Redis 容错 (内存回退)


- [x] 用户画像 ProfileStore (JSON, 置信度合


- [x] 多租户隔(Sidebar Tenant ID, 独立记忆/画像)


- [x] RAGAS 离线评测 (6 Golden Test Set)


  - Faithfulness: 0.38 / AnswerRelevancy: 0.96


  - ContextPrecision: 1.0 / ContextRecall: 1.0





## 更新日志





### 2026-07-25: Docker Compose 部署 + DNS 配置优化


- Docker Desktop 完整安装流程（winget + WSL2 + Ubuntu


- DNS 调整114.114.114.114 解决 Docker Hub IPv6 连接失败问题


- 配置 Daocloud 镜像代理 registry-mirrors 加速镜像拉


- 创建 requirements-docker.txt（精简版，去掉 torch/paddlepaddle 等重型包


- 修改 Dockerfile：从 Daocloud 拉取 python:3.12-slim 基础镜像 + Tsinghua PyPI 镜像


- Docker Compose + docker run 双模式可运行





**启动方式*


`ash


# Docker Compose（推荐）


cd legal-doc-rag


cp .env.example .env


# 编辑 .env 填入 LLM_API_KEY


docker compose up -d





# docker run（无需 Compose


docker run -d --name redis alpine:3.18 sleep infinity


docker run -d --name rag-app -p 8501:8501 --link redis:redis --env-file .env legal-doc-rag_app


`





**注意事项*


- 如果 Docker Hub 连不上（IPv6 超时），修改 DNS 114.114.114.114


- 或配registry-mirrors: https://docker.m.daocloud.io


- pip install 太慢时使用精简requirements-docker.txt


- 首次构建约需 8-10 分钟（pip 下载依赖





### 2026-07-19: RAGAS 评测跑+ ProfileStore + 多租


- RAGAS 评测跑通真实分(豆包 API + 豆包 embedding)


- 新增 ProfileStore: 用户画像独立存储 (置信度加权合


- 多租户隔 Sidebar Tenant ID, 隔离记忆/N/画像


- 修复 EvaluationResult 访问方式 (r.scores 而非 dict)





### 2026-07-19: 接通全部闲置模


- MultimodalPipeline: 替换 PyPDF2 + splitter (图文+OCR)


- HybridRetriever: 替换直接 Chroma retriever (BM25+Dense+RRF)


- QueryRewriter: 检索前 LLM 改写查询


- CitationTracker: 检索结果来源标


- TraceContext: 全链路耗时 + Token 追踪


- 移除 PyPDF2 RecursiveCharacterTextSplitter import





### 2026-07-19: 5 项生产级改进 (memory_manager.py)


1. clear_session: 修复 Redis 僵尸数据 (先清数据再重session_id)


2. 异步访问计数: 检索时反遗(ShadowWorker 批量更新)


3. 实体提取: 实现 _do_extract_entity (原为 pass)


4. 增量摘要合并: 旧摘新对-> LLM -> 合并


5. Redis 容灾恢复: __init__ 末尾调用 _restore_from_redis()





### 2026-07-18: 消除 Monkey Patching


- 删除 original_xxx / patched_xxx / 模块末尾赋


- ForgettingMechanism ShadowWorker 直接内建在类方法


- 修复 extract_entities stub, 添加 memory_llm 回调


- 删除 .orig 备份文件








## 变更记录与面试角





### 1. HybridRetriever (retrieval/hybrid_retriever.py)


改动: BM25 + Dense 双路检+ RRF 融合 + Cross-Encoder 重排


原因: 纯稠密对同义专有名词召回不够, BM25 做关键词补充; RRF 解决两路分数尺度不一


面试可能


- RRF k 值为什么60?  k 控制排名敏感 60 是论文推荐默认


- Cross-Encoder vs Bi-Encoder?  Bi-Encoder 分别编码(, Cross-Encoder 拼一起输, 实践Bi-Encoder 做召 Cross-Encoder 做精





### 2. QueryRewriter (retrieval/query_rewriter.py)


改动: LLM 查询改写, 同义词扩+ 复合问题分解 + 规则兜底


原因: 用户问得模糊时检索效果差


面试可能 改写失败怎么  LLM 失败时返回原查询, 规则级扩展兜





### 3. CitationTracker (retrieval/citation.py)


改动: 检索来源追+ 自动生成引用列表


原因: 回答需要可追溯, 建立用户信任


面试可能 引用怎么实现  检索时记录每个 chunk 的源信息, 拼接上下文时附带 [来源: filename] 标记





### 4. MemorySystem + RedisClient (memory/)


改动: 重构三层记忆(, 集成 Redis TTL 过期 + 内存回退


原因: 单一存储不够; Redis 快速读+ 自动过期适合中期记忆


面试可能


- Redis 不可用时?  自动回退内存存储, 不阻塞对


- TTL 怎么  短期 2h, 中期 24h, 环境变量配置


- 为什么用 Redis?  支持 TTL、List/String 结构适合记忆场景、低延迟





### 5. ForgettingMechanism (memory/forgetting.py)


改动: 艾宾浩斯遗忘曲线记忆衰减 + 自动清理


原因: 记忆无限堆积影响检索质


面试可能 算法公式?  分数=0.5x近因0.3x频率+0.2x重要 近因exp(-小时168)





### 6. MultimodalPipeline + OCREngine (processing/)


改动: PyMuPDF 图文提取 + OCR(PaddleOCR/Tesseract) + 合并分块


原因: PDF 含图片和表格, 纯文本提取会丢失信息


面试可能 PPT/PDF 图怎么处理?  遍历页面提取图片, OCR 识别后缝合进文本 Chunk





### 7. VisionCaptioner (ingestion/vision_caption.py)


改动: Vision LLM 图片标注, 生成 Caption 缝合Chunk


原因: 图片无法直接被检 Caption 实现"搜文字出


面试可能 延迟怎么处理?  异步调用不阻 失败时回退 OCR 文字





### 8. RAGASEvaluator + RegressionRunner (evaluation/)


改动: RAGAS 三维Faithfulness/Relevancy/Recall) + 31 Golden Test Set + 回归历史追踪


原因: 量化评估检索和生成质量, 确保优化不退


面试可能


- 三维度怎么  Faithfulness claim 判断是否被支 Relevancy 反向生成问题算相似度; Recall 判断 ground truth 是否出现在检索结果中


- 测试集怎么设计  31 道题覆盖 10 类法律场 每道question/ground_truth/difficulty





### 9. ShadowWorker (worker/shadow_worker.py)


改动: 异步影子 Worker, 优先级队+ 多线程+ 自动重试


原因: 记忆整理等耗时操作不阻塞主流程


面试可能 Worker 挂了?  任务标记 failed, 可配置重 主进程管Worker 自动恢复





### 10. TenantManager (tenant/tenant_manager.py)


改动: 多租户隔 独立 namespace + ChromaDB Collection + Redis Key 前缀


原因: 多用户数据需隔离


面试可能 怎么隔离?  collection_name = tenant:{id}:knowledge, redis_prefix = tenant:{id}:memory





### 11. TraceContext (observability/tracker.py)


改动: 全链路追 TraceSpan 记录每阶段耗时/Token/异常


原因: 出问题需要定位环


面试可能 影响性能?  不限, 只是计时计数, 内存保留最1000 





### 12. Docker 容器(Dockerfile + docker-compose.yml)


改动: Docker 部署, 编排 app(8501) + redis(6379) 两个服务


原因: 生产环境部署需要容器化, 确保环境一致


面试可能


- 镜像多大?  2-3GB, Python 依赖和模型文


- Redis 挂了?  无法使用记忆功能, 基础检索问答仍可用(回退内存)





## 面试常见问题





### Q1: 为什么用 BM25 + Dense + RRF, 不用纯语义检


BM25 精确匹配关键(条款编号、法律术. Dense 向量捕捉同义词和意译. RRF 无参数融合两路排 纯语义检索漏精确匹配, BM25 漏语义匹





### Q2: Cross-Encoder Bi-Encoder 的区


Bi-Encoder 分别编码 query doc, 速度快但精度 Cross-Encoder query+doc 配对输入, 精度高但 生产: Bi-Encoder 初筛 (top-100), Cross-Encoder 精排 (top-30).





### Q3: 分块大小为什么500?


太小 (128) 语义不完 太大 (1024+) 含多个主题检索不 500 是经验 Overlap 50 防止关键句被切在边界.





### Q4: RAGAS 四个指标怎么


1. Faithfulness: 将回答拆claim, 逐条判断是否被上下文支持. 2. AnswerRelevancy: 从回答反向生成问 与原问题的相似度. 3. ContextPrecision: 检索结果中相关 chunk 的比 4. ContextRecall: ground truth claims 是否出现在检索结果中.





### Q5: 多模PDF 解析怎么做的?


PyMuPDF 提取 PDF 中的图片. Vision LLM (通过 API) 对图片生成描 OCR 提取图片中文 描述+OCR 文字合并到该页的文本 chunk  实现搜文字出





### Q6: 记忆系统怎么设计


三层: 短期(最N 轮原 Redis List TTL 2h), 中期(LLM 摘要, Redis String TTL 24h), 长期(ChromaDB 向量 永久). 后台 Worker 异步整理 >> 遗忘机制基于艾宾浩斯曲线自动过滤低分记忆.





### Q7: 最大的技术挑战是什


Golden Test Set 的设 不同人写ground truth 标准不一致导RAGAS 评分波动. 统一模板: question / ground_truth / source_doc / difficulty. 评估体系稳定后才开始做优化.





### Q8: 为什么不LangChain/LlamaIndex 端到


它们解决的是搭积木的问题 提供现成的组件（ChromaDB 封装、Prompt 模板、文档加载器），让你快速拼出一RAG pipeline。但真正产生价值的地方是关键节点上的定制





1. **检索策*: LangChain as_retriever() 只调 ChromaDB similarity_search，一条腿走路。我们手写了 BM25 + 稠密向量 + RRF 融合 + Cross-Encoder 精排。法律检索同时需要精确匹配条款编号和语义匹配同义表述





2. **记忆系统**: LangChain 自带ConversationBufferMemory 只是把所有历史拼prompt，不做分层、不做摘要压缩、不做遗忘衰减。我们手写了三层记忆（短期原文→中期 LLM 摘要→长期向+ 遗忘曲线）





3. **评测体系**: LangChain 不负责评测。RAGAS 框架能跑分，Golden Test Set（题、答案、context）全是业务层的功夫





**结论**: LangChain/LlamaIndex 当工具用，不当框架用。省掉连 ChromaDB 怎么写这类体力活，但核心问题（检索不准、记忆不强、怎么评估）框架不管，得自己写





### Q9: embedding 模型怎么选？为什么从 text2vec 换成了豆包？


三种方式，改一行代码就能切





| 方式 | 示例 | 费用 | 备注 |


|------|------|------|------|


| 本地模型 | text2vec-base-chinese / BGE | 免费 | 需下载，离线可|


| 在线 API | 豆包 / OpenAI | 按量付费 | 即开即用，无网络问题 |


| 自定| DirectEmbed 包装任意 API | API 而定 | 接口统一，可灵活切换 |





实际项目中的选型原则





1. **原型*: 在线 API 最快跑通。我们最初用 text2vec 本地模型，但服务SSL 证书问题连不huggingface，换成了豆包 embedding API。这是生产中的常见策略降级


2. **上线程*: 如果 QPS 高，切到本地 BGE 模型降本。如query 主要是法律条款精确匹配，BGE 可能比通用 embedding 更合适


3. **维度不是越高越好**: 2560 维对768 维，对单文档问答场景没有肉眼可见的提升，但内存占用高 3 倍。对 10 万级以上的知识库有明显成本差异


4. **很少自己*: 除非有几十万条标注好的三元组（问题，相关文档，不相关文档），否则直接训不如拿 BGE 微调





**面试答案**: embedding 选型是个 trade-off 要离在线、免付费、通用/领域、高低维。关键是你做过取舍，不是背参数表


它们解决的是搭积木的问题 提供现成的组件（ChromaDB 封装、Prompt 模板、文档加载器 让你快速拼出一RAG pipeline。但真正产生价值的地方是关键节点上的定制





1. **检索策*: LangChain as_retriever() 只调 ChromaDB similarity_search, 一条腿走路。我们手写了 BM25 + 稠密向量 + RRF 融合 + Cross-Encoder 精排。法律检索同时需要精确匹配条款编号和语义匹配同义表述





2. **记忆系统**: LangChain 自带ConversationBufferMemory 只是把所有历史拼prompt, 不做分层、不做摘要压缩、不做遗忘衰减。我们手写了三层记忆（短期原文→中期 LLM 摘要→长期向+ 遗忘曲线）





3. **评测体系**: LangChain 不负责评测。RAGAS 框架能跑 Golden Test Set（题、答案、context）全是业务层的功夫





**结论**: LangChain/LlamaIndex 当工具用, 不当框架用。省掉连 ChromaDB 怎么写这类体力活, 但核心问题（检索不准、记忆不强、怎么评估）框架不 得自己写





## 学习建议





1. 先看 streamlit_app.py 理解完整流程 (2 小时)


2. 研究 memory/memory_manager.py 记忆系统 (3 小时)


3. 研究 retrieval/hybrid_retriever.py 混合检(2 小时)


4. 准备面试追问 (2 小时)


5. 不看代码复述项目 (1 小时)


## Docker 部署





### 文件说明


- Dockerfile: python:3.12-slim, 预装依赖 + 可选预下载嵌入模型


- docker-compose.yml: 编排 app + redis 两个服务


- .dockerignore: 排除缓存、本地数





### 使用


```bash


cp .env.example .env   # 填入 LLM_API_KEY


docker compose up -d   # 启动


docker compose logs -f # 日志


docker compose down    # 停止


```





### 服务架构


```


浏览:8501 App(Streamlit) redis://redis:6379


```





### 数据


- model_cache: 嵌入模型缓存(避免每次启动下载)


- memory_db: ChromaDB 持久


- redis_data: Redis AOF 持久





### 16. 流式输出 (streamlit_app.py)


改动: DeepSeek API 改为 SSE 流式输出, 逐字显示回答


原因: 用户体验提升, 感知延迟大幅降低


面试: 流式和普通请求区  stream=True 逐行解析, 边生成边显示





### 17. 用户认证 (streamlit_app.py)


改动: 新增可选密码认 通过 APP_PASSWORD 开


原因: 生产环境需要基本访问控


面试: 为什么不JWT?  Streamlit 单页应用, 密码足够





### 18. 用户反馈 (streamlit_app.py)


改动: 每条回答后增加有没用按钮, 记录feedback_log.json


原因: 收集反馈持续改进 RAG


























### 19. CI/CD (GitHub Actions)


改动: 新增 GitHub Actions CI 工作


原因: 自动语法检+ Golden Test Set 验证


面试可能 CI 跑什么检  语法检查和测试集验





### 20. 健康检(healthcheck.py + docker-compose.yml)


改动: 新增 Docker 健康检


原因: 容器编排需要健康检


面试可能 健康检查怎么实现?  TCP 连接检port 8501








### 21. 结构化日(app/observability/structured_logger.py)


改动: 新增 JSON 结构化日志模 集成到主应用


原因: 生产环境需要可搜索、可聚合的日 RotatingFileHandler 自动轮转


文件:


  - app/observability/structured_logger.py: 日志 JSON 格式, 支持 RotatingFileHandler


  - streamlit_app.py: query 流程中调logger.info()


面试可能 为什么不print?  print 无法按照级别过滤, 不支持结构化输出, RotatingFileHandler 防止日志撑爆磁盘





### 22. 对话持久(app/memory/conversation_store.py)


改动: 新增对话历史持久化到文件, 每次问答后自动保


原因: 用户对话记录需要持久化保存, 支持断点续聊和历史追


文件:


  - app/memory/conversation_store.py: JSON 格式保存对话conversations/ 目录


  - streamlit_app.py: 在问答流程结束后调用 conversation_store.save()


面试可能 为什么不用数据库?  文件存储对单机部署足 JSON 便于人工查看和调





### 23. 查询缓存 (app/retrieval/cache.py)


改动: 新增查询结果缓存, 24h TTL, MD5 作为 key


原因: 相同问题的重复查询直接返回缓存结 减少 API 调用次数和延


文件:


  - app/retrieval/cache.py: 文件级缓 MD5 key, 24h 过期, 自动清理


  - streamlit_app.py: 在查询缓hit 时直接返 miss 时请API 后写入缓


面试可能 缓存过期策略?  24h TTL, 读时惰性删 可扩LRU








### 24. 前端界面重构 (streamlit_app.py)


改动: 全面重写 UI 界面，注入自定义 CSS 主题


原因: 原版 Streamlit 默认样式较为简陋，需要提升用户体验和专业


改动内容:


  - 注入自定CSS: 深蓝导航主题, 圆角卡片, 渐变侧边


  - 侧边栏重 品牌区域 + 分类卡片 + 会话统计 + 版本水印


  - 主区域优 自定义页面标+ 欢迎引导卡片 + 操作步骤提示


  - 消息区域美化: 用户消息蓝底高亮, AI 消息白底卡片, 统一圆角阴影


  - 空状态优 引导用户上传文档的三步指引卡


面试可能 Streamlit 怎么自定义样  st.markdown() 注入 CSS, unsafe_allow_html=True


面试可能 为什么不用前端框  Streamlit 优势在于快速构建数据应 自定CSS 足以达到专业效果








---


---





# 开发踩坑记忆





## 1. DeepSeek 模型名变





DeepSeek 废弃deepseek-chat 模型名（API 返回 400，不发公告）


修复：代码中所有硬编码替换os.getenv(LLM_MODEL, deepseek-v4-pro)env 配置 LLM_MODEL=deepseek-v4-pro





## 2. Embedder Factory：可插拔嵌入





langchain-openai OpenAIEmbeddings 内部tiktoken 将文本转token ID 整数再发API，但豆包 Embedding API 只接受原始文本字符串，导400





修复：自DirectEmbed 类，直接 HTTP 请求发送原始文本字符串。通过 EMBEDDER_TYPE 环境变量控制切换（openai / huggingface），.env 一行即可





## 3. 多次出现的缺失导





开发过程中发现多处函数在模块中定义了但未被导入：TraceContext/get_trace_store（observability.tracker）、QueryRewriter（retrieval.query_rewriter）、CitationTracker（retrieval.citation）、MultimodalPipeline（processing.multimodal_pipeline）、MemorySystem 初始化行丢失





# 面试核心问题清单





Q1: Embedding 为什么不用本地模型而用 API


Embedder 可切换。生产用 API（零 GPU、Docker 镜像 <1GB、冷启动 3 秒），本地开发改一EMBEDDER_TYPE=huggingface。策略模式落地





Q2: Token 成本怎么控制


分层记忆设计。长文本摘要压缩00 token），最近对话原文（600 token），长期语义检索。Embedding API RAG 成本 <5%，LLM 推理才是大头





Q3: 模型名变了怎么办？


环境变量控制模型名，代码 fallback 默认值。DeepSeek 停掉 deepseek-chat 后，改一.env 切换，零代码变更





Q4: 检索不到相关内容怎么办？


混合检索（BM25 + 稠密 + RRF）兜底，LLM 查询改写扩展问题。无结果时返回未找到而非硬编答案，降低幻觉





Q5: 和企业级 RAG 差在哪？


单租户单知识域。企业需多租户隔离、RBAC、限流、A/B 评测、监控。架构可扩展，生产环境加 3-4 个模块





# 环境变量说明





| 变量 | 默认| 说明 |


|------|--------|------|


| LLM_API_KEY | - | DeepSeek API 密钥 |


| LLM_BASE_URL | https://api.deepseek.com/v1 | API 地址 |


| LLM_MODEL | deepseek-v4-pro | 模型名（deepseek-chat 已废弃） |


| EMBEDDER_TYPE | openai | openai / huggingface |


| EMBEDDING_API_KEY | - | 豆包 API 密钥 |


| EMBEDDING_BASE_URL | https://ark.cn-beijing.volces.com/api/v3 | Embedding API 端点 |


| EMBEDDING_MODEL | endpoint ID | Embedding 模型 ID |


| REDIS_URL | redis://localhost:6379/0 | Redis 连接 |


| APP_PASSWORD | - | 可选访问密|








---





## FastAPI 后端026-07-26





### 架构变更





Streamlit 单进程架构切换到 FastAPI REST API + 静态前端





### 文件结构





`


app/


├── main.py               # FastAPI 入口，CORS + 路由挂载


├── api/


  ├── auth.py            # POST /api/auth/register, /api/auth/login


  ├── chat.py            # POST /api/chat (RAG 问答)


  └── documents.py       # POST /api/documents/upload (PDF 上传 + 向量


├── core/


  └── config.py          # 环境变量配置


├── frontend/


  └── index.html         # HTML + JS 前端（登注册/聊天/上传


├── retrieval/             # 复用原有模块


├── processing/            # 复用原有模块


├── memory/                # 复用原有模块


└── tenant/                # 复用原有模块


`





### API 端点





| 方法 | 端点 | 说明 | 认证 |


|------|------|------|------|


| POST | /api/auth/register | 注册新用+ 创建租户 | |


| POST | /api/auth/login | 登录获取 token | |


| POST | /api/documents/upload | 上传 PDF，自动分+ 向量| Bearer Token |


| GET | /api/documents | 列出已上传文| Bearer Token |


| POST | /api/chat | RAG 问答（检+ LLM 生成| Bearer Token |


| GET | /api/health | 健康检| |


| GET | / | 前端页面 | |





### Token 认证机制





登录成功后返token（secrets.token_urlsafe(32)），存储在内存字典中


前端保存localStorage，每次请求通过 Authorization header 传递


Token 无过期时间（生产环境可扩展为 JWT + 过期机制）





### 多租户隔





- 注册时自动创建租户（8字符 UUID


- 文档tenant_id 隔离存储（uploads/{tenant_id}/


- ChromaDB tenant_id 分目录（chroma_db/{tenant_id}/


- 记忆系统tenant_id 隔离





### 前端界面





单页 HTML 应用，包含：


- 登录/注册表单（切换显示）


- 左侧边栏：用户信息、PDF 上传、文档列


- 主区域：聊天消息、引用标注、Token 统计


- 底部输入+ 发送按


- 清除历史、退出登录按





### 启动方式





`ash


# 本地开


pip install fastapi uvicorn python-multipart PyMuPDF


cd D:\git\legal-doc-rag


python -m uvicorn app.main:app --reload --port 8000





# Docker


docker build -t legal-doc-rag-fastapi:latest .


docker run -d --name rag-app -p 8000:8000 legal-doc-rag-fastapi:latest


`





### 环境变量新增





| 变量 | 默认| 说明 |


|------|--------|------|


| JWT_SECRET | legal-rag-secret-key | Token 签名密钥（生产环境需修改|








---





## Docker ?? (2026-07-26)





### Docker ???


- Docker Desktop ???


- C ?????: Docker ????? D:\DockerData





### Docker ???


```bash


cd D:\git\legal-doc-rag


docker build --no-cache -t legal-doc-rag-fastapi:latest -f Dockerfile .


```





### Docker ???


?? `start-rag.bat` (Windows ???) ???


1. ?? Docker Desktop?????????


2. ?? Redis ?? (`rag-redis:6379`)


3. ????? (`rag-app:8000`)


4. ???? http://localhost:8000





### Docker ???


```bash


docker run -d --name rag-redis -p 6379:6379 alpine:3.18 sh -c "apk add --no-cache redis; redis-server --bind 0.0.0.0"


docker run -d --name rag-app -p 8000:8000 --link rag-redis:redis legal-doc-rag-fastapi:latest


```





### ???


```bash


curl http://localhost:8000/api/health


# {"status":"ok","version":"1.0.0"}


```





### Docker ?????


`C:\Users\11195\.docker\daemon.json`:


```json


{


  "registry-mirrors": ["https://docker.m.daocloud.io", "https://docker.1panel.live"],


  "dns": ["114.114.114.114", "8.8.8.8"]


}


```





### API ??


| ??? | ??? | ??? | ??? |


|------|------|------|------|


| POST | /api/auth/register | ??? | ? |


| POST | /api/auth/login | ??? | ? |


| POST | /api/documents/upload | ??? PDF | Bearer Token |


| GET | /api/documents | ????? | Bearer Token |


| POST | /api/chat | RAG ?? | Bearer Token |


| GET | /api/health | ????? | ? |


| GET | / | ??? | ? |





### Docker ??? (?? Docker)


```bash


pip install fastapi uvicorn python-multipart PyMuPDF


cd D:\git\legal-doc-rag


python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000


```





### 25. FastAPI 后端架构 (app/api/ + app/main.py + app/core/)


改动: Streamlit 单文件应用重构为 FastAPI 分层架构


原因: 支持 REST API 对接外部系统，前后端分离，代码职责清新增文件:


  - app/main.py: FastAPI 应用入口，可 uvicorn 独立运行


  - app/api/auth.py: 登录认证 API（POST /api/auth/login  - app/api/chat.py: 问答 API（POST /api/chat/query  - app/api/documents.py: 文档上传 API（POST /api/documents/upload  - app/core/config.py: 集中配置管理（API key、模型名称等  - app/retrieval/embedder_factory.py: Embedding 模型工厂


  - app/tenant/auth.py: 多租户认证逻辑


  - app/frontend/index.html: HTML 前端页面


效果:


  - 旧版本：800+ Streamlit 单文件，UI 和业务逻辑耦合


  - 新版本：Streamlit 只负UI 渲染，业务逻辑通过 FastAPI 模块暴露


  - 外部系统现在可以调用 REST API 直接使用 RAG 能力





### 32. 文件修改生效规则说明


问题: 修改不同文件后，有的立即生效，有的需要重建容器，容易混淆


规则:


  - 本地脚本 (.bat): 改完立即生效（如 start-rag.bat、stop-rag.bat  - 容器配置 (.env, docker-compose.yml): 改完需docker compose up -d --force-recreate


  - 镜像内代(.py): 改完需docker compose build --no-cache app 或用 docker cp 直接拷入容器


  - 容器内配置文(healthcheck.py): 改完后用 docker cp 拷入 + docker restart 即可





### 33. 多文件上传 + 数据持久化 (2026-07-28)

改动: `app/streamlit_app.py`, `docker-compose.yml`

原因: 之前只能上传单个 PDF，上传后文件不保存，容器重启后向量数据丢失

变更:

  - st.file_uploader 改为 accept_multiple_files=True，支持一次选择多个 PDF 上传

  - 处理逻辑改为循环遍历 uploaded_files，逐个解析并合并切块

  - 上传的原始 PDF 保存至 ./uploads/ 目录，通过 Docker volume 持久化

  - ChromaDB 创建时指定 persist_directory="./chroma_db"，调用 .persist()

  - docker-compose.yml 新增 uploads 和 chroma_db 两个 named volume

效果:

  - ✅ 一次上传多个 PDF

  - ✅ 上传的 PDF 保存在容器内 /app/uploads/，不会丢失

  - ✅ 向量数据持久化在 /app/chroma_db/，重启容器不丢失### 34. PDF 删除权限管理 (2026-07-28)

改动: `app/streamlit_app.py`

原因: 用户需要删除已上传的 PDF，但不是所有用户都有这个权限

变更:

  - metadata 新增 "file" 字段，记录每个 chunk 的来源文件名

  - 侧边栏新增"管理已上传文件"区域，只对 super_admin 角色可见

  - 管理员可逐一删除 PDF 文件，同时从 ChromaDB 中清除对应向量

  - 删除通过 ChromaDB Collection.get(where=...) 获取 chunk IDs，再 delete(ids=...)

  - 删除后自动清除 session_state 中的 chunks/retriever/vector_store，触发重建

权限规则:

  - 第一个注册的用户自动获得 super_admin 角色

  - 只有 super_admin 用户能看到删除按钮

  - 普通用户只能上传和提问，无法删除### 35. 超管角色权限升级 (2026-07-28)


改动: pp/tenant/auth.py, pp/streamlit_app.py


原因: 删除文件权限过于宽泛（所有 admin 用户都能删），改为仅 super_admin 可操作


变更:


  - auth.py register(): 第一个注册用户 -> role = "super_admin"，后续用户 -> role = "user"


  - auth.py _init_db(): 自动迁移脚本，将已有 admin 用户升级为 super_admin


  - streamlit_app.py: 删除按钮权限检查从 role == "admin" 改为 role == "super_admin"


权限层级:


  - super_admin: 可上传、提问、删除文件


  - user: 只可上传和提问，看不到删除按钮


### 36. 经典坑: bare except: 吞掉 SystemExit 导致健康检查永远失败 (2026-07-28)


改动: healthcheck.py, docker-compose.yml





**根因（经典到可以当面试题的水平）:**





原始 healthcheck.py:


```python


try:


    r = urllib.request.urlopen("http://localhost:8501", timeout=5)


    exit(0)          # 页面正常 -> 退出码 0


except:              # 裸 except -> 出错了退出码 1


    exit(1)


```





看起来没问题对吧？页面正常就 exit(0)，异常就走 exit(1)。但健康检查永远返回 1。





**关键知识点：Python 的 exit() 不是函数，是异常**





Python 中 `exit()`、`sys.exit()`、`quit()` 的实现机制完全一样：


```python


# Python 内部大致是这样实现的


def exit(code=0):


    raise SystemExit(code)   # <- 抛出一个异常！


```





没错，`exit(0)` 的本质是 `raise SystemExit(0)`。这是一个 **异常对象**，沿着调用栈一路往上冒泡。解释器看到 `SystemExit` 没有被捕获时，才真正退出进程。





**为什么 Python 要这样设计？**





1. 保证清理代码执行：`try-finally` 和 `with` 语句在异常冒泡过程中会执行清理


2. 可以被拦截：调试时可以用 `except SystemExit` 抓住它，打印调用栈再决定是否退出


3. 统一异常机制：不需要为"退出"单独设计一套控制流





**但正是这个好设计，撞上了 Python 最危险的语法：bare except**





```python


try:


    exit(0)              # 抛出 SystemExit(0)


except:                  # <- BARE except = except BaseException:


    exit(1)              # 连 SystemExit 也抓到了！


```





真实运行时发生了什么：





| 步骤 | 代码 | 发生了什么 |


|------|------|-----------|


| 1 | `exit(0)` | Python 抛出 `SystemExit(0)` 异常 |


| 2 | `except:` | 裸 except 捕获了 `SystemExit` |


| 3 | `exit(1)` | 又抛出一个 `SystemExit(1)` |


| 4 | 程序退出 | 退出码 = 1（失败） |





所以健康检查永远返回 exit(1)，Docker 永远 "health: starting"。





**Python 中三种"退出"方式的区别：**





| 函数 | 实现方式 | 能被 except 捕获？ | 执行 finally？ | 推荐使用？ |


|------|---------|-------------------|---------------|-----------|


| `exit(0)` | `raise SystemExit(0)` | 会被 `except:` 捕获；不会被 `except Exception:` 捕获 | 执行 | 交互式环境 |


| `sys.exit(0)` | `raise SystemExit(0)` | 同上 | 执行 | 脚本内推荐 |


| `os._exit(0)` | 直接系统调用 `_exit()` | 不可捕获 | **不**执行 | 仅子进程 fork 后 |





**修复方案：**





修复前：


```python


try:


    r = urllib.request.urlopen("http://localhost:8501", timeout=5)


    exit(0)          # <- 在 try 里 exit，会被 except 吞掉


except:              # <- 裸 except


    exit(1)


```





修复后：


```python


for i in range(5):


    try:


        r = urllib.request.urlopen("http://localhost:8501", timeout=5)


        if r.status == 200:


            sys.exit(0)  # <- 放 try 外面！用 except Exception


    except Exception:    # <- 只捕获 Exception，不碰 SystemExit


        if i < 4:


            time.sleep(2)


        continue


sys.exit(1)


```





关键改动：


  - `exit()` -> `sys.exit()`：功能一样，但 `sys.exit()` 语义更清晰


  - `except:` -> `except Exception:`：不捕获 `SystemExit`、`KeyboardInterrupt`、`GeneratorExit`


  - `sys.exit(0)` 移到了 try 外部：逻辑更清晰，放外面不会被任何 except 捕获


  - 添加 5 次重试（每次 2s）：给 Streamlit 启动时间





**额外修复：**


  - docker-compose.yml: interval 30s -> 15s, timeout 5s -> 15s





**效果:** 容器启动后 ~28s 健康检查通过，页面恢复秒开





**面试官可能会问：**





> Q: `except:` 和 `except Exception:` 有什么区别？


> A: `except:` 等价于 `except BaseException:`，会捕获 SystemExit、KeyboardInterrupt、GeneratorExit。`except Exception:` 只捕获普通的程序异常。


>


> Q: 为什么 Python 不把 SystemExit 设计成继承 Exception？


> A: 因为在 except 语句中，程序员的本意通常是处理程序逻辑错误。如果 SystemExit 继承 Exception，`except Exception` 就会意外拦住程序退出，导致程序关不掉。


> BaseException -> Exception -> 普通异常（ValueError, KeyError 等）


> BaseException -> SystemExit / KeyboardInterrupt / GeneratorExit（不应该被普通 except 捕获）





**记住一句话：**


> Python 中 `exit()` 的本质是 `raise SystemExit()`。它是一个异常，会被 `except:` 捕获。


> **永远不要用裸 `except:`**，至少写 `except Exception:`。


> **永远不要把 `exit()` / `sys.exit()` 放在 try 块里**，会被 except 吞掉。### 37. 错误的 Redis 容器导致页面完全打不开 (2026-07-28)

改动: `docker-compose.yml`

根因: redis 服务的 image 写的是 `alpine:3.18`，但 alpine 基础镜像里没有 Redis 软件。

容器启动后立即退出 → Docker 检测到退出就自动重启（restart: unless-stopped）→ 无限重启循环。

App 容器通过 `depends_on: redis` 依赖这个 Redis 服务，启动后尝试连接 `redis://redis:6379/0`，

但 hostname "redis" 解析到的是这个不断重启的容器，连接永远失败或超时。

修复:

  - image: alpine:3.18 → image: redis:7-alpine（官方 Redis 镜像）

  - 去掉 ports 映射（避免和 rag-project 的 Redis 容器端口冲突，App 走内部 Docker 网络连接）

效果: Redis 容器稳定运行，App 不再等待 Redis 连接，页面秒开

经验: docker-compose 里配 `depends_on` 只保证启动顺序，不保证依赖的服务正常可用。
### 38. 修复: 增量上传多个 PDF 触发重建 (2026-07-28)
改动: app/streamlit_app.py
根因: 上传第二个 PDF 时 vector_store 已存在，直接跳过处理。
修复:
  - 新增 st.session_state.processed_files 追踪已处理的文件名
  - 新增 st.session_state.all_chunks / all_metadatas 跨上传累积所有切块
  - 检测到新文件上传时，自动清空 vector_store 触发重建
  - 重建时 Chroma.from_texts(texts=st.session_state.all_chunks, ...) 使用全部累积数据
流程:
  1. 上传 file1.pdf -> 处理 -> 创建向量库
  2. 上传 file2.pdf -> 检测新文件 -> 清空旧库 -> 合并 file1+file2 切块 -> 重建
  3. 上传 file3.pdf -> 同上 -> 合并所有切块 -> 重建
效果: 支持连续上传多个 PDF 形成稳定的知识库

### 39. 登录/注册切换按钮 (2026-07-28)
改动: app/streamlit_app.py
原因: 之前有用户后只显示登录界面，无法切换到注册页面注册新用户
变更:
  - 新增 st.session_state.auth_page 控制当前显示的认证页面
  - 新增两个 tab 按钮「登录」「注册」可切换
  - 第一个用户时默认注册页，已有用户时默认登录页
效果: 用户可以自由切换登录/注册
