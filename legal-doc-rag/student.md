# 项目吃透指南（Student Notes）

> 本文档整理自对项目 `legal-doc-rag` 的评估，目的是帮助开发者（尤其是面试准备者）从"能跑 demo"到"能吃透、能讲透"这个中文法律文书 RAG 系统。

---

## 一、现状评估（诚实版）

| 维度 | 评价 | 说明 |
|------|------|------|
| **工程完整度** | 强 | 混合检索 / 三层记忆 / 多租户 / 真 JWT+限流+TLS / 单测+集成+评测三层测试 / Docker / 观测，比多数面试 RAG demo 扎实 |
| **业务贴合度** | 强（优势） | 上传法规/合同/文书 → 带引用问答，直接对应法务「法规检索 + 合同审查 + 出具带出处意见」 |
| **检索真实性** | 强 | BM25 + Dense + RRF 召回 + `BGE-Reranker` 真 Cross-Encoder 精排（懒加载 + 优雅降级），不是嘴上 hybrid |
| **多模态真实性** | 中 | PyMuPDF + OCR（PaddleOCR）+ 视觉描述管线存在，但重（CPU/模型依赖），部分部署会退化成纯文字 |
| **评测真实性** | ⚠️ 框架有、跑得少 | 31 条 golden 集 + RAGAS 框架已落地，但真实 RAGAS 评分默认 skip（需 key），别声称"评测充分" |
| **安全** | ⚠️ 有历史债 | 真 JWT / 限流 / TLS 已补；但 Volces embedding key 曾硬编码进源码 = 已泄露，部署前必须轮换 |
| **多租户 / 角色** | 中 | SQLite role 字段 + 每租户独立目录 / 向量库；简单可用，但没讲并发 / 水平扩展 |
| **数据真实性** | 强（优势） | 用真实上传的 PDF 跑，不是 mock 数据，这点比造数据项目更可信 |

### 最大的面试雷区

1. **Embedding key 硬编码泄露史** —— 被问"你做过安全加固吗"要诚实：曾把 Volces key 写进源码（= 已泄露），本轮已移除并改读环境变量，但"部署前必须去平台轮换"。别假装没发生过。
2. **"评测"别吹满** —— 框架在、golden 集只有 31 条、真实 RAGAS 默认 skip。正确说法："我搭了 RAGAS 评测管线 + 31 条回归集，真实评分在有 key 时跑，默认离线校验 harness，确保不回归。"
3. **多模态别当标配** —— OCR / 视觉模型重，可能退化。讲清"何时走多模态、何时纯文字"。
4. **"混合检索"被追问 Cross-Encoder 是否真加载** —— 答：`BGE-Reranker` 懒加载，不可用时优雅跳过（RRF 结果直接当 Top-K），所以即使 reranker 没起来，系统仍可用。

---

## 二、如何吃透：四层理解法

不要背代码，按这四层建立"能讲出来"的认知。

### 第 1 层｜架构层（能白板画出）

- 分层：用户层（前端 / Streamlit / SSE）→ 安全层（JWT 校验 + 限流 + TLS + 错误统一处理）→ 应用层（FastAPI：`auth`/`documents`/`chat`/…）→ 核心层（检索 / 记忆 / 处理 / 评测）→ 基础设施（ChromaDB 向量库 / Redis 记忆 / 模型服务 DeepSeek + BGE-M3）
- 关键文件：`app/main.py`（装配 + 限流器注册）、`docker-compose.yml`（拓扑：app + redis）、`app/retrieval/hybrid_retriever.py`（检索核心）

### 第 2 层｜数据流层（一条请求的生命周期）

**文档 ingestion（上传 → 入库）：**

```
上传 PDF → [安全] JWT + 限流 → 落盘（按租户目录）
        → PDF 提取（PyMuPDF 文字 + 图片坐标）
        → OCR（PaddleOCR）/ 视觉描述（可选多模态）
        → 分块（≈500 字符）
        → Embedding（BGE-M3，1024 维）→ 写入 ChromaDB（每租户独立集合）
        → Shadow Worker 异步：摘要（中期记忆）+ 实体画像
```

**问答 query（一次 RAG 链路）：**

```
POST /api/chat（Bearer）→ [安全] JWT 校验 + 限流
  → 取短期记忆（Redis）→ query_rewrite（查询改写）
  → hybrid_retrieve：BM25（关键词）+ Dense（向量）→ RRF 融合召回 50
  → Cross-Encoder（BGE-Reranker）精排 Top-5 → 引用拼接（citation）
  → 拼 prompt → LLM（DeepSeek，原始 HTTP /chat/completions）流式 SSE
  → 落三层记忆（短期原文 / 中期摘要 / 长期向量 + 遗忘曲线）→ 返回
  （异步）Shadow Worker 更新摘要 / 画像
```

每一步的输入 / 输出 / 兜底：看 `app/api/chat.py` 的 try/except 与 `_get_reranker()` 懒加载逻辑就很清楚。

### 第 3 层｜模块层（逐个击破）

| 模块 | 路径 | 你要能讲清的 |
|------|------|------|
| 检索 | `app/retrieval/` | BM25 + Dense + RRF 怎么融合；Cross-Encoder 精排为何后接；citation 怎么定位原文；embedding 工厂怎么切本地 / 线上 |
| 记忆 | `app/memory/` | 三层各自存什么、TTL、遗忘曲线干嘛、Redis 挂了怎么降级 |
| 处理 / 多模态 | `app/processing/` | PyMuPDF vs OCR 何时用；视觉描述管线成本；分块策略 |
| 安全 | `app/security/` + `app/core/limiter.py` | 真 JWT 签名 / 过期；限流策略（20 / 100 per min）；TLS 全开；错误统一处理 |
| 租户 | `app/tenant/` | 每租户目录 + 向量库隔离；role 字段权限 |
| 观测 | `app/observability/` | 全链路追踪 / Token 统计 / 结构化日志用来干嘛 |
| 评测 | `app/evaluation/` | RAGAS 四指标；golden 集；真实评分为何默认 skip |
| Worker | `app/worker/` | Shadow Worker 异步摘要 / 画像；Webhook 重试（60s 轮询，最多 5 次） |
| API | `app/api/` | 路由划分；`require_user` 公共依赖；流式 SSE 实现 |

### 第 4 层｜取舍与改进层（面试加分项）

每个技术选型能答 why / why not：

- 为什么本地 **BGE-M3** 而非线上 embedding：零成本 / 零泄露 / 面试加分"检索不依赖外部服务"；但切换后需清空 `chroma_db` 重新向量化。
- 为什么 **hybrid** 而非纯语义：低频法律术语语义易漏，BM25 兜底。
- 为什么自己写 RAG 而非 LangChain：可控 / 可读 / 面试能讲清每一步；但承认 LangChain 生态省事。
- SQLite → 多租户隔离怎么切；并发 / 水平扩展怎么讲（当前单实例）。

---

## 三、结合法律业务背景，最高效的吃法

最大的优势是**这是法务场景的数字化**。把项目模块映射成真实工作：

- 上传法规 / 合同 = 建立可检索的法规库 / 合同库
- 带引用问答 = 出具"有出处"的法律意见（避免编造法条 → 法律风险）
- 反馈 👍/👎 = 回答质量闭环
- RAGAS 评测 = 防止"幻觉法条"的量化手段
- 多租户 = 不同律所 / 客户数据隔离

**用"如果这是律所 / 公司法务部的辅助工具，我会怎么改"的视角去读代码**，记忆会非常牢固，面试也能讲出业务 insight 而非纯技术八股。

---

## 四、自测：达到"吃透"的 3 个标准

1. ✅ 不看书，白板画出架构图 + 一条问答的完整链路（含检索 / 重排 / 记忆 / LLM）
2. ✅ 能现场改一个小功能（比如：给回答里每条引用加"跳转原文高亮"；或按法规分类筛选检索）
3. ✅ 能回答下一节的 5 个高频题，且不踩上面雷区（key 泄露要诚实讲）

---

## 五、面试高频自测题

1. 为什么混合检索（BM25 + Dense + RRF）不用纯语义？低频法律术语语义易漏召回，BM25 提供关键词兜底，RRF 融合保证召回。
2. Cross-Encoder 重排怎么接？为什么先召回 50 再精排 Top-5？Bi-Encoder 离线向量化适合召回，Cross-Encoder 交互式适合精排；先召回再精排是延迟 / 成本权衡；且 reranker 不可用时优雅降级。
3. 三层记忆怎么设计？各解决什么问题？遗忘曲线干嘛？短期（Redis 原文，TTL 2h）保连贯；中期（LLM 摘要，TTL 24h）压缩；长期（ChromaDB 向量 + 遗忘曲线）跨会话沉淀。遗忘曲线淘汰低价值记忆省成本。
4. Embedding 为什么选本地 BGE-M3？你做过哪些安全加固？本地零成本 / 零泄露；安全上曾硬编码 Volces key（= 泄露），已移除改环境变量且部署前需轮换，同时补了真 JWT / 限流 / TLS。
5. 怎么量化 RAG 效果、防"编造法条"？RAGAS 四指标（faithfulness / answer_relevancy / context_precision / context_recall）+ 31 条 golden 回归集；真实评分有 key 才跑，默认离线 harness 防回归。
6. （加分）多租户隔离怎么做？高并发 / 水平扩展你怎么讲？

---

## 六、版本演进速览

| 里程碑 | 日期 | 内容 |
|--------|------|------|
| P2 高级功能 | 2025-08-04 | 知识库分组 / 多轮对话管理 / Elasticsearch 全文检索 / A-B 测试 / Webhook |
| 安全加固 | 2026-08-04 | 真 JWT + 限流 + TLS + 去硬编码 key + integration/evaluation 测试补齐 |
| 测试修复 | 2026-08-05 | 单元测试 32/32 绿；删临时脚本；清理 debug 输出 |
| 整洁度 | 2026-08-05（续） | Webhook 重试真正生效；整体测试 44 passed / 1 skipped |

> 详见 `README.md` 的「面试常见问题」「踩过的坑」「更新日志」三节，里面 Q1–Q8 与 17 个实战坑是高频素材。

---

## 七、架构速记图（MVC 对照 + 双数据流）

> 如果你学过 MVC，直接把项目对齐三层：**Controller = app/api/\***（只收 HTTP、鉴权、调服务）；**Service = retrieval/processing/memory/security/tenant**（业务逻辑）；**Model = Chroma 向量库 / SQLite / uploads / cache / memory_db**（持久化）；**View = API 返回的 JSON**。下面三张图已生成为 SVG（`docs/images/*.svg`），任何 Markdown 预览器 / GitHub / VS Code 都能直接显示；同时保留第二节 ASCII 版供离线速读。

### 图 1 · MVC 三层对照

![图 1 · MVC 三层对照](docs/images/mvc.svg)

> 每个 Model 组件都按 `{tenant_id}` 子目录物理隔离（如 `chroma_db/<tenant_id>/`），不是"共享库 + 租户字段"。

### 图 2 · 数据流一：上传 / 入库（写进去）

![图 2 · 上传/入库数据流](docs/images/ingestion.svg)

- **红色 = security 把关**：`get_safe_upload_path` 把 `tenant_id` 只留 `[a-zA-Z0-9_-]`、清洗文件名，再用 `is_safe_path`（resolve 后判断仍在 base 内）防 `../` 穿越。
- 关键 API：`app/api/documents.py:39`（落盘路径）、`:56`（建 Chroma 并 persist）。

### 图 3 · 数据流二：查询 / 问答（读出来）

![图 3 · 查询/问答数据流](docs/images/query.svg)

- **橙色 = 重排环节**：语义召回后精排，避免"相关但不准"的法条；reranker 不可用时优雅降级（RRF 结果直接当 Top-K）。
- 关键 API：`app/api/chat.py:162`（`_build_pipeline` 载入 `chroma_db/<tenant>` + QueryCache + QueryRewriter + CitationTracker）。

### 自测默写卡（先想再核对）

1. **用 MVC 类比，Controller / Service / Model / View 分别是什么？**
   Controller = `app/api/*` 路由（documents/chat/auth/admin/feedback.py），只管收 HTTP、鉴权、调服务；Service = retrieval / processing / memory / security / tenant（业务逻辑）；Model = Chroma 向量库、SQLite、uploads、cache、memory_db（持久化）；View = API 返回的 JSON。

2. **上传一个 PDF 后，数据经过哪些步骤才落盘？**
   `POST /upload` → `require_user` 解 JWT 得 `tenant_id` → `get_safe_upload_path` 写到 `uploads/<tenant>/<safe>.pdf` → `MultimodalPipeline` 切块 → BGE-M3 embedder 向量化 → `Chroma.from_texts(persist_directory=chroma_db/<tenant>).persist()`。返回 `{success, chunks, tenant_id}`。

3. **查询时，一条用户问题如何变成带引用的答案？**
   JWT→`tenant_id` → `_build_pipeline` 载入 `chroma_db/<tenant>` → `QueryRewriter`(LLM) 改写 → Chroma 相似检索 top-k → `BGE-Reranker` 精排 → DeepSeek 生成 + `CitationTracker` → 返回带 `source` 引用的 JSON。

4. **"按租户目录落盘"具体怎么实现？为什么不会串租户或越权？**
   根目录（`UPLOAD_DIR` / `CHROMA_PERSIST_DIR`）+ `tenant_id` 拼子目录，每个租户独立文件夹。安全靠 `get_safe_upload_path`：`tenant_id` 只留 `[a-zA-Z0-9_-]`、文件名清洗、`is_safe_path` 用 `resolve` 后判断仍在 base 内，防 `../` 穿越。

5. **检索为什么是 hybrid + reranker，而不是纯语义向量？**
   法律术语要精确匹配（BM25/关键词）避免语义漂移漏掉关键法条；向量召回语义相似片段；再用 BGE Cross-Encoder 重排提升 top-k 精度，且不可用时优雅降级——这是 RAG 不胡说的关键一环。

6. **三层记忆系统存什么、按什么隔离？**
   会话/短期、用户长期偏好、知识库级记忆；按 `tenant_id` 目录（`memory_db/<tenant>`）与 Redis 前缀（`tenant:{id}:memory`）做物理 + 前缀隔离。

> 能流畅答出上面 6 张卡 = 吃透。建议配合第三节"白板默写"一起练。

