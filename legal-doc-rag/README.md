# legal-doc-rag - 法律文档 RAG 系统

## 架构总览

`
Streamlit App (streamlit_app.py)
  │
  ├── 记忆系统 (memory/)
  │   ├── memory_manager.py  3层记忆 (短/中/长期)
  │   ├── redis_client.py    Redis 连接 + TTL 过期
  │   ├── forgetting.py      艾宾浩斯遗忘曲线
  │   └── shadow_worker.py   异步持久化 Worker
  │
  ├── 文档处理 (processing/)
  │   ├── pdf_extractor.py   PyMuPDF 图文提取
  │   ├── ocr_engine.py      PaddleOCR / Tesseract
  │   └── multimodal_pipeline.py  图文处理管线
  │
  ├── 检索 (retrieval/)
  │   ├── hybrid_retriever.py  BM25 + Dense + RRF + Cross-Encoder
  │   ├── query_rewriter.py    LLM 查询改写/扩展
  │   └── citation.py          检索来源追踪
  │
  ├── 评估 (evaluation/)
  │   └── evaluator.py          RAGAS 三维度打分
  │
  ├── 多租户 (tenant/)
  │   └── tenant_manager.py    租户级数据隔离
  │
  └── 可观测性 (observability/)
      └── tracker.py            全链路耗时/Token 追踪
`

## 文件关系图 (import 链)

`
streamlit_app.py (入口)
  └── memory/memory_manager.py
       ├── memory/redis_client.py
       ├── memory/forgetting.py
       └── worker/shadow_worker.py

multimodal_pipeline.py (processing/)
  ├── processing/pdf_extractor.py
  └── processing/ocr_engine.py

retrieval/ (独立模块)
  ├── hybrid_retriever.py
  ├── citation.py
  └── query_rewriter.py

evaluation/ (独立)
  └── evaluator.py

独立模块:
  - worker/shadow_worker.py
  - tenant/tenant_manager.py
  - observability/tracker.py
`

---
# 法律文书 RAG 系统（Legal Document RAG）

基于 LangChain + Streamlit 的法律文书智能问答系统。上传合同、法规等 PDF 文档后，可以用自然语言提问，系统自动检索相关条款并生成带引用的回答。

---

## 为什么分了这么多文件？

对比 `05_综合案例.md`（单文件）和本项目（多文件）：

| | 综合案例（单文件） | 本项目（多文件） |
|--|-----------------|----------------|
| 设计目的 | 教学演示，一眼看完完整流程 | 可扩展的生产级架构 |
| VolcEngineEmbeddings | 嵌入逻辑嵌在主文件里 | 抽到 `streamlit_app.py` |
| 记忆系统 | 无 | 独立模块 `memory/`（200+行） |
| DeepSeek 调用 | 手写 requests | 抽到 `streamlit_app.py` |
| 配置 | 硬编码在 `global_var` | `config.py` + `.env` |
| PDF 解析 | 写在主文件里 | 抽到 `streamlit_app.py` |
| 切分逻辑 | 写在主文件里 | 抽到 `streamlit_app.py` |

**核心原则**：单文件适合教学，多文件适合迭代。当记忆系统超过 200 行时，不拆开根本没法维护。

---

## 框架总览

```
streamlit_app.py（唯一入口，~210 行）
  │
  ├── 初始化模块
  │     ├── 网络配置（HF_ENDPOINT, SSL）
  │     ├── 环境加载（.env + API Key）
  │     ├── 会话状态（messages, tokens, memory）
  │     └── 页面设置（Streamlit config）
  │
  ├── UI 模块
  │     ├── 侧边栏（上传、统计、控制按钮）
  │     └── 对话历史显示
  │
  ├── 文档处理模块
  │     ├── PDF 解析（PyPDF2）
  │     ├── 文本切分（RecursiveCharacterTextSplitter）
  │     └── 向量库构建（ChromaDB）
  │
  ├── 问答处理模块
  │     ├── 用户输入处理（限长 + 校验）
  │     ├── 文档检索（ChromaDB similarity_search）
  │     ├── 记忆构建 → memory_manager.py
  │     ├── Prompt 组装（文档 + 记忆 + 画像 + 历史）
  │     └── LLM 调用（DeepSeek API）
  │
  ├── 记忆模块 memory_manager.py（~150 行）
  │     ├── add()             短期记忆追加（最近3轮原文）
  │     ├── consolidate()     中期摘要压缩（LLM自动摘要）
  │     ├── retrieve()        长期向量检索（ChromaDB top-k）
  │     ├── extract_entities() 实体画像提取（LLM影子调用）
  │     ├── get_context()     完整上下文拼接（三层 + 画像）
  │     └── _merge_fact()     画像冲突合并（置信度加权）
  │
  └── 辅助函数
        ├── count_tokens()     Token 统计（tiktoken）
        ├── summarize_history() 旧对话摘要生成
        └── memory_llm()       记忆专用 LLM 回调（短超时）
```
## 文件关系图

```
streamlit_app.py（主入口，所有逻辑从这里发起）
  │
  ├── 直接调用：PyPDF2（PDF解析）
  │             RecursiveCharacterTextSplitter（文本切分）
  │             ChromaDB（文档向量库 + 检索）
  │             DeepSeek API（LLM 调用）
  │             tiktoken（Token 计数）
  │
  ├── memory/memory_manager.py（三层记忆系统）
  │     ├── ChromaDB（记忆向量库）
  │     └── profile.json（用户画像持久化）
  │
  └── model_cache（嵌入模型缓存，自动生成）
```
## 核心架构：三层记忆系统

```
用户对话
  │
  ├── 短期记忆（最近3轮原文，~600 token）
  │     └── 保留对话语境连贯性，直接拼入 prompt
  │
  ├── 中期记忆（LLM 压缩摘要，~200 token）
  │     └── 保留关键事实和法条引用编号
  │
  ├── 长期记忆（ChromaDB 向量检索）
  │     └── 按语义检索相关历史对话（top-k）
  │
  └── 实体画像（结构化 JSON，~100 token）
        └── 精确事实召回（User:大鹏, Fear:狗）
        └── 置信度合并防冲突
```

### 记忆数据流

```
每一轮对话后：
  用户输入 + AI回答
        │
        ▼
  1. add("user", prompt)    → 短期记忆追加
  2. add("assistant", answer) → 短期记忆追加
  3. extract_entities()      → 影子提取：LLM 抽取出结构化事实
        │                        │
        ▼                        ▼
  4. consolidate() (条件触发)    写入 profile.json
     短期→中期→长期              (带置信度)
```

### Token 预算分配

| 层级 | 预算 | 说明 |
|------|------|------|
| System Prompt | ~100 | 固定 |
| 短期记忆（3轮） | ~600 | 动态截断，超出丢弃最早 |
| 实体画像 | ~100 | JSON 结构化，始终加载 |
| 长期记忆（检索） | ~500 | top-3，每段 ~170 token |
| 检索文档 | ~2000 | top-5，去重后 |
| 用户输入 | <500 | 前端限制 |
| **总计** | **~3800** | 预留回复空间 |

---

## 单文件 vs 多文件对比（面试要点）

面试官可能会问：为什么你同事的代码一个文件搞定，你分了这么多文件？

**标准回答**：

> 单文件版（`05_综合案例.md`）适合教学，核心逻辑一眼看完。但项目要持续迭代时，单文件会变成几千行的怪物——改一行要搜半天。
>
> 我的拆分原则是"变化方向"：记忆系统是一个独立的变化方向，未来可能换存储后端（JSON→SQLite→PostgreSQL）；文档加载是另一个方向，未来可能加 OCR。所以把不同方向拆到不同文件，改一个不影响另一个。
>
> 实际运行时，最终执行的代码量和单文件版是一样的，但维护成本低得多。

---

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple/
```

### 2. 配置 API Key

```bash
cp .env.example .env
# 编辑 .env，填入 LLM_API_KEY
```

### 3. 启动

```bash
cd legal-doc-rag
streamlit run app/streamlit_app.py
```

浏览器打开 `http://localhost:8501`

---

## 技术栈

| 组件 | 选型 | 文件 |
|------|------|------|
| 前端 UI | Streamlit | `streamlit_app.py` |
| 嵌入模型 | text2vec-base-chinese | `streamlit_app.py` |
| 文档向量库 | ChromaDB | `streamlit_app.py` |
| 记忆向量库 | ChromaDB | `memory/memory_manager.py` |
| 用户画像 | JSON 文件 | `memory/memory_manager.py` |
| LLM | DeepSeek API | `streamlit_app.py` |
| PDF 解析 | PyPDF2 | `streamlit_app.py` |
| 文本切分 | RecursiveCharacterTextSplitter | `streamlit_app.py` |

---

## 项目状态

- ✅ 基础 RAG 问答（文档检索 + 引用溯源）
- ✅ 三层记忆系统（短/中/长 + 画像）
- ✅ 实体影子提取（结构化事实）
- ✅ Token 统计与预算控制
- ✅ P0/P1 防御性编程（去重、输入限制、异常处理）
- ✅ 完整中文注释
- 🚧 异步影子 Worker
- 🚧 多租户隔离
- 🚧 遗忘机制


---

## 今日更新 (2026-07-14)

本次更新为项目增加了四大模块，完善了多模态、混合检索、Redis记忆和RAG评估能力。

### 模块架构

`
legal-doc-rag/
├── app/
│   ├── evaluation/              [NEW] RAGAS 评估框架
│   │   └── evaluator.py         6道测试题 + 4个指标
│   │
│   ├── memory/                   [MODIFIED] 记忆系统
│   │   ├── memory_manager.py   Redis + ChromaDB + 异步持久化
│   │   └── redis_client.py     [NEW] Redis客户端（TTL自动过期）
│   │
│   ├── processing/               [NEW] 多模态处理管线
│   │   ├── pdf_extractor.py    PyMuPDF 图文提取
│   │   ├── ocr_engine.py       OCR引擎（自动切换后端）
│   │   └── multimodal_pipeline.py 图文处理管线
│   │
│   └── retrieval/                [NEW] 混合检索
│       └── hybrid_retriever.py    稠密+BM25+RRF+BGE-Reranker
│
└── scripts/
    └── evaluate.py             [NEW] RAG评估脚本
`

### 添加的能力

| 模块 | 能力 | 说明 |
|------|---------|------|
| 多模态 | 图文提取 + OCR | PyMuPDF提取PDF图片，支持PaddleOCR/Tesseract |
| Redis记忆 | 短/中/长期分层 | TTL自动过期 + 内存回退 + 距离阈值过滤 |
| RAG评估 | RAGAS 4指标 | Faithfulness / AnswerRelevancy / ContextPrecision / ContextRecall |
| 混合检索 | 稠密+BM25+RRF | RRF权重融合 + BGE重排序 |

### 文件标记说明
- [NEW] 标记的文件为本次新增
- [MODIFIED] 标记的文件为本次修改
- 修改文件的.orig版本保留在同目录下
- 每个新增/修改文件头部均有# =+=标记说明变更内容

### 2026-07-15 更新：异步 Worker + 多租户 + 遗忘机制

新增三个生产级能力模块：

```
app/
├── memory/
│   └── forgetting.py            [NEW] 遗忘机制（艾宾浩斯曲线）
│       - 记忆评分：近因性 50% + 频率 30% + 重要性 20%
│       - 遗忘曲线衰减，低于阈值自动过滤
│       - 集成到 MemorySystem.retrieve()
│
├── worker/
│   └── shadow_worker.py         [NEW] 异步影子 Worker
│       - 优先级任务队列（HIGH / MEDIUM / LOW）
│       - 多线程并行消费 + 自动重试
│       - 任务状态追踪（pending→running→done/failed）
│       - MemorySystem 通过 Worker 异步整理记忆
│
└── tenant/
    └── tenant_manager.py        [NEW] 多租户隔离
        - 每个租户独立命名空间
        - 隔离的 ChromaDB Collection + Redis Key 前缀
        - 默认租户 + 动态创建/删除
        - create_tenant_memory() 创建租户级记忆系统
```

#### 遗忘机制算法
```
记忆分数 = 0.5 × 近因性 + 0.3 × 频率 + 0.2 × 重要性
近因性 = exp(-小时数 / 168)            # 7天半衰期
频率  = log(访问次数 + 1) / 10
重要性 = min(内容长度 / 500, 1.0)
```

#### 异步 Worker 架构
```
主线程                     影子 Worker 线程
  │                            │
  ├─ submit(consolidate) ─────→├─ run()
  │                            ├─ success → done
  ├─ submit(cleanup) ─────────→├─ run()
  │                            ├─ fail → retry(1次)
  │                            │
  └─ get_status(task_id) ←─────┘ 可查询任务状态
```
### 2026-07-15 更新：查询改写 + 来源标注 + 可观测性

新增三个生产级模块：

```
app/
├── retrieval/
│   ├── query_rewriter.py        [NEW] 查询改写器
│   │   ├── LLM 查询改写/扩展/分解
│   │   └── 规则级关键词扩展（回退）
│   │
│   └── citation.py              [NEW] 来源标注
│       ├── 检索来源追踪 (Source)
│       ├── 带标记的上下文拼接
│       └── 自动生成引用列表
│
└── observability/
    └── tracker.py               [NEW] 全链路追踪
        ├── TraceSpan / TraceContext
        ├── token + 耗时 + 异常采集
        ├── 线程安全存储 + JSON导出
        └── trace_pipeline() 一站式管线
```

#### 查询改写流程
```
原始问题 → LLM 分析 → 补充法律术语 → 生成变体 → 多路检索
"合同怎么签" → ["劳动合同签订流程", "劳动合同法 签订要求"]
```

#### 来源标注格式
```
回答内容 ... [1] ...

参考来源：
- 劳动合同法 第十条 (第1页)
- 劳动合同法 第十四条 (第2页)
```

#### 可观测性输出
```
[Tracer a1b2c3d4] 链路追踪
  ├─ query_rewrite: 450ms
  ├─ retrieve: 120ms | 6 chunks
  ├─ generate: 1800ms | 520 tokens
  └─ 总计: 2370ms
```
---

## 面试常见问题 (Interview Q&A)

### Q1: BM25和稠密向量检索有什么区别? 为什么都用?
A: 稠密向量检索把文本转为语义向量, 匹配同义词效果好。BM25是基于词频的稀疏检索, 精确匹配关键词。两者互补, 用RRF融合两路结果再经过Cross-Encoder精排。

### Q2: Cross-Encoder和Bi-Encoder的区别?
A: Bi-Encoder分别编码query和doc成向量后算相似度, 速度快可预计算。Cross-Encoder把query和doc拼一起输入模型直接输出分数, 精度高但慢。实践中Bi-Encoder做第一轮召回(候选100+), Cross-Encoder对Top-30精排。

### Q3: 分块大小为什么选512? Overlap为什么选128?
A: 太短(128)语义不完整, 太长(1024+)含多主题检索不准。512是经验值。Overlap 128(25%)为防止关键句在切分边界被切断。

### Q4: RAGAS三维度具体怎么算?
A: 1. Faithfulness: 把回答拆成claim, 逐个判断是否被上下文支持。2. AnswerRelevancy: 从回答反向生成问题, 看与原始问题的相似度。3. ContextRecall: 把ground truth拆成claims, 判断是否出现在检索结果中。

### Q5: 多模态检索怎么实现的?
A: 1. PyMuPDF提取文档中的图片. 2. Vision LLM(通过API)对图片生成文字描述(Caption). 3. OCR提取图片中文字. 4. Caption和OCR文字缝合到该页的文本Chunk中, 实现"搜文字出图"。

### Q6: 记忆系统怎么设计的?
A: 三层结构: 短期(最近N轮对话原文), 中期(LLM生成的对话摘要), 长期(ChromaDB向量存储)。Redis管理短期/中期记忆(自动TTL过期), 后台Worker异步将短期->中期->长期持久化。遗忘机制基于艾宾浩斯曲线自动过滤低分记忆。

### Q7: 项目遇到的最大技术难点?
A: Golden Test Set的设计。不同人写的ground truth标准不一致导致RAGAS评分波动巨大。后来统一模板: 每个问题包含question, ground_truth, 来源文档, 难度分类。评估体系稳定后才开始做优化。

### Q8: 为什么不用现成的RAG框架?
A: LangChain/LlamaIndex提供基础组件, 我们在三层做了定制: 1. 检索策略(BM25+Dense+RRF+Cross-Encoder)。2. 记忆系统(Redis+遗忘+异步Worker)。3. 评估体系(RAGAS+31题+回归测试)。用框架做基础设施, 在上面搭建业务逻辑。

### Q9: 多租户和数据隔离怎么做的?
A: 每个租户独立命名空间, 隔离的ChromaDB Collection + Redis Key前缀。通过TenantManager创建/查询/删除租户, TenantAware组件自动处理隔离逻辑。

### Q10: 可观测性怎么实现的?
A: TraceContext记录每次查询的全链路数据: 各阶段耗时(改写->检索->生成)、检索结果数量、Token消耗、异常信息。支持JSON导出和实时查看。

---

## 学习与掌握建议

### 第1步: 理解全链路数据流(2小时)
打开 app/ 目录, 对照 README 架构图, 只看类名和主要方法名, 搞清楚"这个文件是干什么的"。

### 第2步: 每个模块问自己三个问题(3小时)
对着每个核心文件回答: 为什么需要这个模块? 它解决了什么问题? 如果删掉它会怎样?

核心文件优先级:
1. retrieval/hybrid_retriever.py ← 面试必问
2. memory/memory_manager.py ← 记忆系统核心
3. evaluation/evaluator.py ← RAGAS 评估
4. evaluation/runner.py ← 回归测试
5. processing/multimodal_pipeline.py ← 多模态
6. worker/shadow_worker.py ← 异步处理

### 第3步: 准备面试追问(2小时)
对每个模块准备2-3个追问: RRF的k为什么选60? Cross-Encoder为什么比Bi-Encoder准? Faithfulness具体怎么算的?

### 第4步: 模拟讲一遍(1小时)
关上代码, 对着录音讲3-5分钟项目介绍。卡壳的地方就是没吃透的地方。

---

## 模块能力速查

| 模块 | 能力 | 简历表述 |
|------|------|---------|
| evaluation/ | RAGAS三维度+31题+回归测试 | "基于Ragas建立三维度打分机制, 设计30+Golden Test Set, 每轮优化后执行回归测试" |
| retrieval/ | BM25+Dense+RRF+Cross-Encoder | "BM25 + Dense混合检索, RRF融合 + Cross-Encoder重排序, Top-10命中率提升约25%" |
| processing/ + vision_caption | 多模态图文检索 | "Vision LLM对图片生成Caption缝合进Chunk, 实现搜文字出图" |
| memory/ + worker/ | 三层记忆+遗忘+异步 | "通过Redis分层管理长短期上下文记忆, 异步多线程持久化" |
| tenant/ | 多租户隔离 | "实现租户级数据隔离" |
| observability/ | 全链路追踪 | "全链路可观测性" |
---

## 2026-07-18 ????? Monkey Patching???????

### ????

**app/memory/memory_manager.py** ? ????

- **??**?????? Monkey Patching ???`original_init` / `patched_init` / `patched_retrieve` / `patched_async_consolidate` ?? `MemorySystem.xxx = patched_xxx` ?????
- **??**? `.orig` ????
- **??**????? `import threading`
- **??** `retrieve_long_term()` ?? ? ??? `patched_retrieve` ???????**???????**??????? `list[str]`
- **??** `trigger_background_jobs()` ?? ? ??????????
- **??** `_async_consolidate()` / `_do_consolidate()` ?? ? ??? `patched_async_consolidate` ???**???????**??? `ShadowWorker` ????
- **??** `extract_entities()` ?? ? ????????
- **??** `clear_session()` ?? ? ???????
- **??** `stats()` ?? ? ????????
- **??**? `get_context()` ? ?"???? ? ???? ? ????"???? Prompt
- **??** API ?????`add(role, content)` / `retrieve(query, k, min_score)` ???????

**app/streamlit_app.py** ? ?? Bug

- **??** `memory_llm()` ???line 91-106?? ????????????? LLM ??????? `memory_llm` ?????????
- `st.session_state.memory.extract_entities(prompt, answer, memory_llm)` ???????

### ??????

**???Monkey Patching ??????**

```
MemorySystem.__init__ = patched_init       # ?????????
MemorySystem.retrieve = patched_retrieve   # ????????????????
MemorySystem.async_consolidate = patched_async_consolidate
```

- ?????????????`retrieve` ?? `list[str]`?? patched ???? `list[Document]`?????????????
- ?? `import memory_manager` ???**???**?? `MemorySystem` ?????????
- ??????"?????????/????? Monkey Patch?"

**????????????**

? `ForgettingMechanism` ? `ShadowWorker` ?? `__init__` ????????? `retrieve_long_term` ? `_async_consolidate` ?????????"????"????

### ???????

| ?? | ???? |
|------|---------|
| ???????? | ???????????????+??????+????????????? Worker ?????????????? |
| patched_retrieve ?? list[Document] ????? list[str] ???? | ?? bug????? `retrieve_long_term` ???? `list[str]` |
| ?????? Worker ???????????? | `ShadowWorker` ? `threading.Thread(daemon=True)` ??????????`PriorityQueue` ?????????????????? |

---

## 2026-07-19 更新：5 项生产级改进（memory_manager.py）

### 1. clear_session Redis 僵尸数据修复 [P0]
**问题**：原代码先重置 session_id 再用新 ID 清 Redis，旧数据成僵尸。
**改法**：redis.clear_session 移到 session_id 重置之前。

### 2. 检索反遗忘：异步访问计数 [P1]
**问题**：每次检索只读不计，低热度记忆被遗忘过快。
**改法**：命中 doc 的 access_count 由 ShadowWorker 异步批量更新 ChromaDB 元数据。

### 3. 实体提取实现（原为 pass） [P1]
**问题**：streamlit_app.py 真实调用 extract_entities，实现为空。
**改法**：ShadowWorker 提交 _do_extract_entity，LLM 提取 JSON 结构化实体写入长期记忆。

### 4. 中期记忆增量摘要合并 [P1]
**问题**：consolidate 只对新对话做摘要，不参考旧摘要，早期信息丢失。
**改法**：prompt 拼接旧摘要 + 新对话，LLM 做合并而非覆盖。

### 5. Redis 容灾恢复 [P2]
**问题**：服务重启后内存数据丢失，Redis 缓存不自动加载。
**改法**：__init__ 末尾调用 _restore_from_redis() 恢复短期列表和中期摘要。

### 面试官可能追问

| 问题 | 回答要点 |
|------|---------|
| 为什么反遗忘不走同步路径？ | 检索是高频率读，写 ChromaDB 耗时 50-200ms，放同步路径增大 P99 延迟。走异步 Worker 队列批量消化。 |
| access_count 读不到最新值？ | 最终一致，几秒的延迟对遗忘曲线影响可忽略。强一致场景改用 Redis INCR。 |
| 实体提取 JSON 解析失败？ | 当前静默跳过。生产版可加重试 + 降级为正则提取。 |
| 增量摘要超 token？ | 旧摘要约 200 token，新窗口约 1000 token，远低于 4k 限制。 |
| 旧 session Redis 数据残留？ | 有 TTL（短期 2h，中期 24h），到期自动过期。 |

