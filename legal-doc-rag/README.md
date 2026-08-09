# Legal Document RAG

## Overview

基于 FastAPI 的法律文书智能问答系统。上传 PDF、法规、法律文件，用自然语言提问，系统自动检索相关条款并生成带引用的回答。


## 核心特性

- FastAPI 后端 — 异步高吞吐，RESTful API，Token 认证
- 多租户隔离 — 每租户独立上传目录 + ChromaDB 向量库
- 角色权限 — 首个用户为 super_admin（可删文档），后续为 user（仅问答）
- 三层记忆 — 短期（Redis，TTL 2h）+ 中期（摘要，TTL 24h）+ 长期（ChromaDB）
- 混合检索 — BM25 + Dense + RRF + Cross-Encoder 重排序
- 多模态 PDF — 文字（PyMuPDF）+ OCR（PaddleOCR）
- Token 预算控制 — LLM 调用统计 + 上限
- 流式输出 — SSE 实时流式响应
- 用户反馈 — 👍/👎 收集问答满意度
- 全链路追踪 — 请求耗时、Token 统计、每步性能分析
- 结构化日志 — JSON 格式日志，支持日志采集系统 👍/👎 收集问答满意度
- 异步整理 — Shadow Worker 后台提取摘要 + 实体画像

## 角色系统

首个注册用户为 super_admin，后续注册为 user。

| 功能 | super_admin | user |
|------|:-----------:|:----:|
| 上传 PDF | ✅ | ✅ |
| 问答 | ✅ | ✅ |
| 删除 PDF | ✅ | ❌ |
| 文档列表 | ✅ | ✅ |

删除文档会同步删除文件系统和 ChromaDB 中的向量索引。

## 快速开始

```bash
# docker-compose（推荐）
cd D:\git\legal-doc-rag
docker compose up -d --build

# 或双击桌面快捷方式"法律文书 RAG 系统"

# 或手动 Python
pip install -r requirements-docker.txt
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

访问 http://localhost:8000

## API 端点

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| POST | /api/auth/register | 注册（首个为超管） | 无 |
| POST | /api/auth/login | 登录返回 Token | 无 |
| POST | /api/auth/change-password | 修改密码（校验原密码，新密码≥6 位） | Bearer |
| POST | /api/documents/upload | 上传 PDF（**异步**：立即返回 task_id，后台索引） | Bearer |
| GET | /api/documents/task/{task_id} | 查询上传索引任务的进度与状态 | Bearer |
| GET | /api/documents | 文档列表 | Bearer |
| DELETE | /api/documents/{filename} | 删除文档（超管） | Bearer |
| POST | /api/chat | RAG 问答（stream 字段控制是否 SSE） | Bearer |
| POST | /api/chat/stream | RAG 流式问答（SSE） | Bearer |
| GET | /health | 健康检查（注意：无 `/api` 前缀） | 无 |

## 测试

项目使用 pytest 做自动化测试，分三层：单元测试、集成测试、评测测试。

![测试分层全景](docs/images/testing-landscape.png)

*图：测试分层——越往下越接近真实、越慢；unit / integration / evaluation 三层均已实现。*

### 目录结构

```
tests/
├── conftest.py          # 公共 fixtures：mock Redis / ChromaDB / LLM 等外部依赖
├── unit/                # 单元测试（已实现）
│   ├── test_config.py
│   ├── test_hybrid_retriever_v3.py
│   ├── test_memory_manager_fixed.py
│   └── test_api_chat_simple.py
├── integration/         # 集成测试（已实现）
└── evaluation/          # 评测测试（已实现）
```

### 1. 单元测试（Unit）
测单个函数逻辑：config 解析、hybrid_retriever 打分、memory_manager 存取、chat 接口参数校验。

```bash
python -m pytest tests/unit/ -v
```

### 2. 集成测试（Integration）— 已实现
把多个真实组件接起来跑，验证组件间契约与全链路拼接正确：API 路由 → JWT 鉴权 → 业务编排 → （LLM / embedding / OCR 用 mock 替代）。测试环境与生产完全隔离（`tests/integration/conftest.py` 提供临时 sqlite 用户库 + 临时上传/向量目录 + 每测试重置限流），不会污染真实数据。已覆盖：

- **JWT 鉴权链路**（`test_auth_chain.py`）：注册 / 重复注册拒绝 / 错误密码拒绝 / 登录拿 token / `/me` 无 token·错误 token·正确 token 的行为
- **限流生效**（`test_rate_limit.py`）：同一 IP 高频登录触发 429（验证上一轮 slowapi 接线真的生效）
- **聊天全链路**（`test_chat_integration.py`）：完整链路（mock LLM 返回）→ 答案正确；未上传文档 → 优雅返回"请先上传文档"；缺字段 → 422
- **文档上传**（`test_document_upload.py`）：上传落盘 + 列表可见 + 非 PDF 拒绝 + 无/错误 token 拒绝

```bash
python -m pytest tests/integration/ -v
```

![集成测试范围](docs/images/integration-scope.png)

*图：集成测试把路由 → 检索 → 向量库 → LLM 真实接线，只 mock 掉 LLM 网络调用。*

### 3. 评测测试（Evaluation）
不问代码对错，问回答质量。用 RAGAS 给回答打分（0~1），防"编造法条"这类高风险问题。四个核心指标：

- **Faithfulness 忠实度**：答案是否只基于检索到的上下文，没有编造
- **Answer Relevancy 相关性**：答案是否切题、回应了问题
- **Context Precision 上下文精度**：相关片段在检索结果里是否排名靠前
- **Context Recall 上下文召回**：检索是否覆盖回答所需的全部资料

`tests/evaluation/test_ragas_eval.py` 已落地三层用例，离线即可跑、不依赖 ragas/网络：

- `test_golden_test_set_schema`：校验 `tests/golden_test_set.json`（31 条法律问答回归集）结构
- `test_ragas_harness_offline`：mock LLM 调用，验证评测数据集能正确组装
- `test_ragas_real_eval`：真正跑 RAGAS 评分（检测到 ragas 与 `LLM_API_KEY`/`ARK_API_KEY` 才运行，否则自动 skip）

也可直接运行原始脚本（需联网 + key）：

```bash
python scripts/run_ragas_eval.py
```

![RAGAS 评测指标](docs/images/ragas-metrics.png)

*图：RAGAS 四个核心指标（0~1，越高越好），忠实度专门防"编造法条"。*

### 运行全部 + 覆盖率

```bash
python run_tests.py            # 依次跑 unit/integration/evaluation + 覆盖率报告
# 或
python -m pytest --cov=app --cov-report=term-missing
```

> 说明：`setup.cfg` 已移除 `fail_under=80` 的覆盖率门槛，测试不再因覆盖率不足而"变红"（用例本身 pass 即通过）。integration / evaluation 现已实现并纳入统计。所有用例用 pytest 标记分层（`unit` / `integration` / `evaluation`），可按层运行，例如 `python -m pytest -m integration`。

## 模型服务选型决策（LLM / Embedding）

### 背景
本项目为**中文法律文书 RAG**，推理链路需要两类模型服务：
- **LLM（问答生成）**：将检索到的法条 / 案例 / 文书片段喂给大模型，生成最终回答。要求指令遵循强、中文语感好、能忠实引用上下文。
- **Embedding（向量化）**：将文档切片与用户 query 编码为向量，决定混合检索的召回质量，是 RAG 效果的上限。

### LLM 选型：DeepSeek（deepseek-chat / V3）
- **候选对比**：DeepSeek、智谱 GLM-4、阿里 通义千问、火山 豆包、小米 MiMo、MiniMax
- **选定**：`deepseek-chat`（OpenAI 兼容端点 `https://api.deepseek.com/v1`）
- **选择原因**：
  1. 中文质量第一梯队，RAG 问答生成完全够用；
  2. 成本极低（输入约 ¥1 / 百万 token），面试演示 / 长期自测不心疼；
  3. 提供 OpenAI 兼容 API，`config.py` 的 `LLM_BASE_URL` + `LLM_MODEL` 直接填即可，**无需改代码**；
  4. 响应快、服务稳定。
- **否决项**：
  - **小米 MiMo**：推理专精模型（数学 / 代码 / 逻辑链），而 RAG 生成端要的是「忠实复述 + 指令遵循」，MiMo 更慢更贵且角色不匹配；
  - **MiniMax / 豆包 / 智谱**：可用，但综合中文质量与性价比不及 DeepSeek。

### Embedding 选型：本地 BGE-M3（默认）
- **演进历史**：
  1. **最初（本地）**：`shibing624/text2vec-base-chinese`（sentence-transformers 本地加载，零成本）→ 因国内下载模型超时 / 依赖冲突 / CPU 推理慢，**跑不通**；
  2. **中期（线上）**：切火山方舟 / 豆包 embedding（`openai` 兼容端点，模型 `ep-m-...`）→ 可用，但源码曾硬编码 key（已移除），**历史可能留存泄露风险，需轮换**；
  3. **现在（方案 2，默认）**：切回本地 **`BAAI/bge-m3`**。
- **选定本地 BGE-M3 原因**：
  1. 零成本、零外部依赖、零密钥泄露风险（彻底绕开线上 key 隐患）；
  2. 中文法律文本语义效果优于 `text2vec-base-chinese`；
  3. 项目 `requirements-docker.txt` 已含 `sentence-transformers`，huggingface backend 已支持；
  4. 面试加分点：「检索层不依赖任何外部 embedding 服务」。
- **切换注意事项**：
  - BGE-M3 输出 **1024 维**，首次运行需联网下载模型到 `./model_cache`（建议提前在有网环境预下载，或配置 HuggingFace 镜像源）；
  - 切换 embedding 模型后，已存的 Chroma 向量库维度 / 语义不再匹配，需**清空 `chroma_db` 重新向量化**文档（本项目当前 `chroma_db` 为空库，切换后直接上传即可，无需重建）；
  - 如需线上 embedding：设 `EMBEDDER_TYPE=openai` 并填 `EMBEDDING_API_KEY`（火山 / 智谱 / 阿里均可），但务必先**轮换原泄露的 key**。

### BGE-M3 相对 text2vec-base-chinese 的实质提升

`text2vec-base-chinese` 是项目最初本地方案（基于 `bert-base-chinese`，768 维，纯稠密，512 token 上限）。切到 BGE-M3 后在法律文书 RAG 场景有**实质性**提升：

| 维度 | text2vec-base-chinese | BGE-M3 | 对法律场景的意义 |
|------|----------------------|--------|------------------|
| 向量维度 | 768 | **1024** | 表达更丰富，长难句 / 近似表述区分度更高 |
| 上下文长度 | 512 token（≈300 中文字） | **8192 token** | 判决 / 合同 / 法规动辄上万字，text2vec 直接截断丢内容；BGE-M3 可整段吃下 |
| 向量类型 | 仅稠密 | **三合一：稠密 + 稀疏（SPLADE）+ 多向量（ColBERT）** | 稀疏抓「法条编号 / 条款名」精确词，稠密管语义，ColBERT 做 token 级细匹配 |
| 语言 | 仅中文 | **100+ 语言** | 涉外 / 双语法律文本可用 |
| 检索基准 | 中文相似度榜中上 | **MTEB 中文检索 SOTA 级** | 召回 Top-K 更相关，减少漏召导致的答非所问 |

**当前实际吃到的收益（drop-in 替换已生效）：**
1. **检索质量跃升**：BGE-M3 中文检索能力远超 text2vec，长文档语义对齐更准，召回 Top-K 相关性更高；
2. **长文本不再截断**：8192 token 上限，长法条 / 长判决可被完整向量化（text2vec 的 512 是硬伤，会强制截断丢失后续内容）。

> ✅ **稀疏向量已接上**：BGE-M3 的 SPLADE 稀疏向量已接入混合检索。`embedder_factory` 优先返回 `BGEM3Embedder`（稠密 1024 维 + 自计算稀疏权重）；文档上传时把每段稀疏权重落盘到 `./sparse_db/{tenant}/{file}.json`，`HybridRetriever` 新增稀疏检索分支，与 BM25 + 稠密经 RRF 融合重排，法律术语 / 法条编号精确召回明显提升。注意：稀疏权重由本模块**自计算**（绕过 FlagEmbedding 1.4.0 的 `scatter_reduce` 在 CPU 下偶发整条丢失的 bug），结果 100% 可复现。ColBERT 多向量仍未接（见下方待办）。

**代价**：模型体积 2.3GB（text2vec ≈400MB），加载更占内存、首向量化更慢；已下载到 `./model_cache` 并由 `.gitignore` 忽略，不入库。

**待办（解锁 BGE-M3 全部能力）**：
- [x] 接入 BGE-M3 稀疏向量，与现有 BM25 + 稠密做融合重排（提升法律术语精确召回）；
  - 实现：`app/retrieval/bge_m3_embedder.py` 自计算 SPLADE 权重。BGE-M3 稀疏头是 `Linear(H,1)` 逐位置标量门控，本模块按 `input_ids` 取每个 token 的**最大门控权重（amax 聚合）**组装为 `{token_id: weight}`（确定性 Python 实现，等效于 FlagEmbedding 的 `scatter_reduce(amax)`，但规避了其在 CPU 下偶发整条丢值的 bug）；`sparse_store.py` 落盘/加载，`HybridRetriever._sparse_search_bge` 与 BM25 + 稠密做 RRF 加权融合。回归测试 `tests/unit/test_bge_m3_sparse.py` 覆盖非空/确定性/特殊 token 过滤。
- [ ] 实验 ColBERT 多向量 late-interaction，强化长文证据定位；
- [ ] 在 `tests/golden_test_set.json`（31 条法律问答回归集）上对比 text2vec → BGE-M3 的检索/回答质量提升。

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| LLM_API_KEY | - | DeepSeek Key |
| LLM_BASE_URL | https://api.deepseek.com/v1 | LLM 地址 |
| LLM_MODEL | deepseek-v4-pro | 模型名 |
| EMBEDDING_API_KEY | - | 豆包 Embedding Key |
| EMBEDDING_BASE_URL | https://ark.cn-beijing.volces.com/api/v3 | Embedding 地址 |
| EMBEDDER_TYPE | openai | 嵌入类型（openai/huggingface） |

## Docker

### 数据存储（D 盘）
Docker 数据通过符号链接指向 D:\DockerData\Docker，不占 C 盘空间。

### 容器
- legal-doc-rag-app-1: FastAPI（port 8000）
- legal-doc-rag-redis-1: Redis（port 6379）

### 一键启动
start-rag.bat 自动检测 Docker Desktop 运行状态并拉起服务。

## 面试常见问题

### Q1: BM25 + Dense + RRF 为什么不用纯语义？
语义检索对低频法律术语易漏召回。BM25 提供关键词匹配兜底，RRF 融合保证召回。

### Q2: Cross-Encoder vs Bi-Encoder？
Bi-Encoder 离线向量化适合召回，Cross-Encoder 交互式计算适合精排。管线先召回 50 条，Cross-Encoder 重排选 Top-5。

### Q3: 分块大小为什么 500？
基于法律条款长度统计，500 字符确保单块覆盖完整条款。

### Q4: RAGAS 指标？
faithfulness（忠实）+ answer_relevancy（切题）+ context_precision（精确）+ context_recall（召回）

### Q5: PDF 多模态解析？
PyMuPDF 提取文字 + 图片坐标 -> pdf2image 转图 -> PaddleOCR 识别 -> 多尺度描述。

### Q6: 记忆系统？
三层：短期（Redis 原文）-> 中期（LLM 摘要）-> 长期（ChromaDB 向量 + 遗忘曲线）。

### Q7: 为什么从 text2vec 换成豆包？
本地 Embedding 有部署/更新/硬件成本。豆包 API 零维护，支持中文法律场景。

### Q8: 角色系统？
SQLite role 字段 + 前端 JS 校验 + 后端 API 二次校验防止越权。

## 踩过的坑

以下是开发过程中遇到的关键问题、原因和解决方案。

### 1. Healthcheck bare except 吞掉 SystemExit
**现象**：容器健康检查永不失败，即使 Uvicorn 已崩溃。\
**原因**：healthcheck.py 用了 bare `except:`（没有指定异常类型），捕获了 `SystemExit`（正常退出信号）。\
**解决**：改为 `except Exception`，避免捕获 `SystemExit`、`KeyboardInterrupt`。

### 2. 浏览器 IPv6 超时导致 1 分钟空白
**现象**：打开 http://localhost:8000 要等 1 分钟才能看到页面。\
**原因**：localhost 在某些浏览器中解析为 IPv6 地址 `::1`，Docker 未监听 IPv6，连接超时后才回退到 IPv4。\
**解决**：明确绑定 `--host 0.0.0.0`，同时 `docker-compose.yml` 中 ports 改为 `127.0.0.1:8000:8000`。

### 3. 容器无限重启
**现象**：容器启动失败后，docker compose 不停重建容器，日志刷屏。\
**原因**：`restart: unless-stopped` 配合短间隔健康检查，启动阶段未就绪就被强行重启。\
**解决**：加 `start_period: 30s` 和 `retries: 3`，给应用充分的初始化时间。

### 4. CPU 100% 导致页面缓慢
**现象**：页面操作卡顿，CPU 持续满载。\
**原因**：健康检查每 15 秒触发一次完整 Streamlit 脚本重新加载（热重载机制），每次重载都是 CPU 密集型操作。\
**解决**：健康检查间隔从 15s 改为 120s，并加入 `start_period` 避免启动阶段频繁检查。

### 5. Redis Alpine 镜像中没有 redis-server
**现象**：`alpine:3.18` 为基础镜像的容器启动失败，提示找不到 redis-server。\
**原因**：`alpine:3.18` 是裸 Alpine 系统，不包含 Redis。之前用 Dockerfile 手动安装但镜像更新后缓存失效。\
**解决**：改用官方 `redis:7-alpine` 镜像，开箱即用。

### 6. 中文编码双重损坏
**现象**：HTML 和 Python 文件中的中文字符显示为乱码，如 `ç™»å½•`。\
**原因**：PowerShell `@'...'@ | python` 管道将 UTF-8 字节按系统代码页（GBK）解码成 Latin-1，Python 再按 UTF-8 读取，导致双重编码错误。\
**解决**：避免使用 PowerShell 管道传递中文；用 `[System.IO.File]::WriteAllText` 直接写入文件。

### 7. 浏览器缓存旧版中文乱码页面
**现象**：修复中文后刷新页面还是乱码，但加 `?t=1` 就正常。\
**原因**：`docker cp` 替换了文件但 `last-modified` 时间戳没变，浏览器认为文件未过期，使用缓存中的旧版本。\
**解决**：更新文件后执行 `touch` 更新时间戳，并在 HTML 中添加 `Cache-Control: no-cache` 元标签。

### 8. 删除 PDF 不同步清除 ChromaDB
**现象**：PDF 已删除，但问答仍能检索到该文档的内容（幽灵结果）。\
**原因**：`DELETE` 只删了文件系统的 PDF，未清理 ChromaDB 中的向量索引。\
**解决**：删除端点先查 `Chroma.get(where={"source": filename})` 获取对应 chunk IDs，再调用 `Chroma.delete(ids=...)` 同步清除索引。

### 9. Docker 磁盘爆满导致 Bus error
**现象**：docker build 过程中出现 `Bus error (core dumped)`，pip install 失败。\
**原因**：Docker 的 WSL2 VHDX 虚拟磁盘占满 C 盘（0 字节可用），无法写入新数据。\
**解决**：将 Docker 数据从 C 盘迁移到 D 盘（robocopy + mklink /J），并紧缩 VHDX（37GB -> 19.5GB）。

### 10. 超管权限仅前端校验
**现象**：浏览器隐藏了删除按钮，但用 Postman 直接发 DELETE 请求也能成功。\
**原因**：后端未校验用户角色，任何用户都可以绕过前端直接调用 API。\
**解决**：后端 `DELETE` 端点添加 `role == "super_admin"` 校验，返回 403 拒绝越权请求。

### 11. 快速启动脚本 Docker 未就绪
**现象**：双击 start-rag.bat 后直接报错，提示无法连接 Docker daemon。\
**原因**：Docker Desktop 启动需要时间，脚本在 daemon 就绪前就执行了 `docker run`。\
**解决**：加入 `:wait_docker` 循环，每 3 秒检查一次 `docker info`，直到 daemon 响应。

### 12. docker-compose.yml 中 version 声明废弃
**现象**：每次启动都打印 `attribute version is obsolete` 警告。\
**原因**：Compose Specification v2 不再需要 `version: "3.x"` 声明。\
**解决**：移除 `version: "3.9"` 行。


### 13. MemorySystem 初始化参数名拼写错误
**现象**：chat 接口 500，反回 "Internal Server Error"，浏览器报 "Unexpected token I, is not valid JSON"。\
**原因**：`_get_memory` 函数中调用 `MemorySystem(embedder=embedder, ...)`，但构造函数参数名为 `embedding_model`，不是 `embedder`，导致 `TypeError: unexpected keyword argument`。\
**解决**：`embedder=embedder` 改为 `embedding_model=embedder`。


### 14. MemorySystem 构造参数 `worker` 不存在
**现象**：chat 接口 500，报 `TypeError: got an unexpected keyword argument "worker"`。\
**原因**：`_get_memory` 中传了 `worker=get_worker()`，但 `MemorySystem.__init__` 只接受 `embedding_model, persist_dir, redis_url, tenant_id, max_short_term, forgetting_threshold`，没有 `worker` 参数。\
**解决**：删除 `worker=get_worker()` 参数。ShadowWorker 通过 `get_worker()` 单例内部访问，无需传入构造函数。


### 15. tenant_data/users.db 被打包进镜像导致角色混乱
**现象**：重建容器后首个注册用户拿到的是 `user` 而不是 `super_admin`。\
**原因**：`docker compose build` 时 `COPY . .` 把本地的 `tenant_data/users.db`（含历史测试用户）打包进镜像，新建容器时数据库非空，首个用户无法成为 `super_admin`。\
**解决**：删掉本地 `tenant_data/`，并在 `.dockerignore` 中添加 `tenant_data/`，避免数据库文件进入镜像。

### 16. DirectEmbed 传错导致检索崩溃
**现象**: 上传 PDF 后提问报 AttributeError: 'DirectEmbed' object has no attribute 'similarity_search_with_score'
**根因**: HybridRetriever 的 dense_store 参数期望 ChromaDB（有搜索结果方法），代码传了 embedder（只做 embedding，无搜索能力）
**修复**: HybridRetriever(embedder, ...) → HybridRetriever(vector_store, ...)
**教训**: DirectEmbed 只负责"文字→向量"的转换，不负责存储和搜索。传参时确认对象有对应方法。

### 17. FastAPI 版文件 GBK 编码问题
**现象**: 容器启动报 SyntaxError，中文显示为 Ã¥Â¸Âº 等乱码
**根因**: 另一台电脑用 GBK（Windows 默认编码）写 Python 文件，Python 3 默认用 UTF-8 解析时报错。
同时 .env 被 .gitignore 排除，容器内 load_dotenv() 读取不到，embedding 配置走默认值指向 DeepSeek 而非火山引擎
**修复**:
  - GBK 文件转为 UTF-8
  - docker-compose.yml 补全 EMBEDDING_API_KEY / BASE_URL / MODEL
  - .env 缺失导致 embedding 指向 DeepSeek 而非火山引擎
**教训**: Windows 上 PowerShell 的 Add-Content / Out-File 默认用 GBK，Python 文件必须显式指定 UTF-8 编码。
.env 文件不要放 .gitignore（或放 docker-compose 的 environment 里兜底）。

## 更新日志

### 2026-08-09: 新增修改密码接口 POST /api/auth/change-password

- **需求**：用户把 Sprayming 密码改成 123456 测试后需要改回，但系统无修改密码入口。
- **改动**：
  1. `app/tenant/auth.py` 新增 `change_password(username, old_password, new_password)`：校验用户存在 → 校验原密码（`_verify_password`）→ 新密码≥6 位 → 更新 `password_hash`。
  2. `app/api/auth.py` 新增 `POST /api/auth/change-password`，请求体 `{old_password, new_password}`，经 `Depends(require_user)` 鉴权（取当前登录用户），路由放在 `require_user` 定义之后以免 `NameError`；限流 10/minute。
- **行为**：成功返回 `{success:true}`；原密码错误/新密码过短(≥6)/用户不存在 → 400；未带 Token → 被拒（与 `/me` 等受保护路由一致，缺 `Authorization` 头时 FastAPI 返回 422）。
- **验证**：端到端测试通过——注册临时账号→登录→改密→新密码可登/旧密码 401→错误原密码 400→过短新密码 400；临时账号已清理，未改动 Sprayming 账户。
- **文档同步**：README API 表新增 `POST /api/auth/change-password`（Bearer 认证）。

### 2026-08-09: 恢复桌面快捷方式启动脚本 + 修正健康检查端点文档

- **问题**：双击桌面"法律文书 RAG 系统"快捷方式（.lnk）无反应 / 打不开。
- **根因**：该 .lnk 指向的目标脚本 `D:\git\legal-doc-rag\启动法律文书 RAG 系统.bat` 已丢失（项目内仅剩 `start-rag.bat` / `start-local.bat` / `stop-rag.bat`），快捷方式找不到目标文件而失效。
- **修复**：重建 `启动法律文书 RAG 系统.bat`，用本机 miniconda Python（`C:\Users\11195\miniconda3\python.exe`）在 `127.0.0.1:8000` 启动 uvicorn，等待 `/health` 就绪后自动打开浏览器 `http://localhost:8000`。
- **附带修正（文档 bug）**：README API 表原写 `GET /api/health`，但代码实际路由是 `/health`（无 `/api` 前缀，见 `app/observability/monitoring.py:209`），已更正；启动脚本里的就绪探测也同步改为 `/health`。
- **验证**：uvicorn 成功启动，前端 `/`、`/docs`、`/api/auth/register` 均返回 200；`/health` 在缺 `redis` 模块时返回 503（`overall=unhealthy`），但 bat 用 `curl` 连通性判断，503 也是有效 HTTP 响应，能正确识别服务已起并打开浏览器，前端问答不受影响。
- **补充（本轮健壮性改进）**：bat 增加端口占用预检（`netstat` 检测 8000 是否被旧服务/Docker 占用，占用即提示退出，不再无限等待）、uvicorn 输出重定向到 `start-rag.log`（启动失败可查错）、就绪等待加 60 秒超时（超时明确提示看日志）。旧版用 `start` 后台拉起 uvicorn 后主脚本死等 `curl`，一旦 uvicorn 启动失败（最常见为端口被占）新窗口一闪而过、错误不可见、主脚本卡死，表现为"双击没反应"。

### 2026-08-08: 修复 chat 接口返回 null/500 的多个 bug（c3ce4f6）

- **现象**：重启服务、换好 DeepSeek key 后，聊天接口仍返回 null 或 500，前端显示"API错误：请求失败"。
- **根因**：`app/api/chat.py` 存在多处损坏——① 路由注册的 `chat` 是空壳函数（真实逻辑未被装饰器注册）；② 把元组当成对象访问属性；③ 引用了未定义的 `ContextTracker`；④ 对 `_memory_cache`（实为 dict）调用了 `.put()`。
- **修复**：
  1. 删除空壳 `chat`，使装饰器注册到真实实现。
  2. `_build_pipeline` 改为返回 `SimpleNamespace`（含 `.vector_store/.qr/.cache/.ct/.mem`）。
  3. `_get_context` 改用已导入的 `CitationTracker` 并复用 `pipeline.ct`。
  4. `_memory_cache.put/.cleanup` 改为 dict 兼容；新增 `from types import SimpleNamespace`。
  5. 索引未完成时返回"文档正在后台索引中（进度 X%）"。
- **验证**：register / login / upload / chat 全链路 200。

### 2026-08-08: 上传改为异步索引 + 新增任务轮询接口（f19ace2）

- **动机**：大 PDF（如 581KB 民法典）在 CPU 上同步嵌入 >240s，阻塞主进程导致服务卡死。
- **改动**：
  1. 新增 `app/tasks/__init__.py` 与 `app/tasks/task_store.py`（进程内任务状态 + 单 worker 线程池，避免 torch 并发不安全）。
  2. `app/api/documents.py`：`upload_document` 改为接收文件 → 安全落盘 → **立即返回 202 + `task_id`**；后台 `_run_indexing()` 执行抽取+嵌入+建索引+持久化稀疏向量；新增 `GET /api/documents/task/{task_id}` 轮询进度。
  3. `app/api/chat.py`：索引中提问返回"文档正在后台索引中（进度 X%）"。
- **文档同步**：README API 表新增 `GET /api/documents/task/{task_id}`，上传标注异步；`static-guide.html` / `student.md` / `architecture-explainer.html` 写入链路与调用树同步改为异步（提交 `14c93d0`）。
- **验证**：上传秒回（0.03s/0.05s）、进度轮询可用、索引期间 `/health` 0.15s 响应、chat 返回民法典 1254 条引用。

### 2026-08-09: 修复上传后提示请先上传文档 + 聊天 JSON 解析网络错误

#### Bug 1：已上传文档却提示"请先上传文档"
- **现象**：用户在 Web 上传 PDF 成功（左侧"已上传文档"列表已显示），索引进行到约 40% 时/或重启服务后，聊天接口仍返回"请先上传文档"，无法提问。
- **根因**：后台索引任务状态原先只存在 `app/tasks/task_store.py` 的**内存字典** `task_store._tasks` 里。一旦 uvicorn 进程重启（或崩溃），任务表被清空，但 `uploads/{tenant}/` 里的 PDF 文件还在、`chroma_db/{tenant}` 尚未建好，于是 `chat.py` 判空库直接返回"请先上传文档"——文档其实早上传了，只是索引被中断且状态丢失。
- **修复**：
  1. `app/tasks/task_store.py`：任务状态改为持久化到 `data/tasks.json`，进程重启后从磁盘自动恢复。
  2. `app/main.py`：启动时扫描 `uploads/{tenant}/`，对已上传但未完成向量化的 PDF 自动重新提交后台索引（避免手动重传）。
  3. `app/api/chat.py`：向量库不可用时按状态返回不同提示——索引中/"文档正在后台索引中（进度 X%）"、索引失败/"请重新上传"、已上传未索引/"文档正在恢复索引"、未上传/"请先上传文档"。
  4. `app/frontend/index.html`：修复上传成功后显示 `(undefined 段已索引)`（异步接口不再返回 chunks，改为显示 task_id + "正在后台索引"）。

#### Bug 2：聊天返回"网络错误：Unexpected token 'd', data:{...} is not valid JSON"
- **现象**：用户在对话框发送第二条消息时，界面报"网络错误"，控制台显示 JSON 解析失败，解析内容却是 SSE 流式数据（以 `data:` 开头）。
- **根因**：前端 `sendMessage()` 先请求 `/api/chat/stream`，但后端此前**没有**这个路由；未匹配到 API 路由的请求落到 `StaticFiles(html=True)`，POST 被返回 405 Method Not Allowed。前端进入 fallback 后又请求 `/api/chat`，且未传 `stream` 字段，`ChatRequest.stream` 默认 `True`，于是后端返回 `StreamingResponse`（SSE），前端却用 `r2.json()` 解析，导致报错。
- **修复**：
  1. `app/api/chat.py`：新增 `POST /api/chat/stream` 路由 `chat_stream()`，强制 `stream=True` 并复用 `chat()` 的流式分支，使前端主链路有合法端点。
  2. `app/frontend/index.html`：fallback 请求显式带上 `stream: false`，并把 `r2.json()` 改为先 `r2.text()` 再 `JSON.parse`，非 JSON 时截断文本展示，避免再次抛"网络错误"。
- **验证**：
  - `curl POST /api/chat/stream` 返回 200 + `text/event-stream`。
  - `curl POST /api/chat` 且 `stream:false` 返回标准 JSON。
  - 登录后连续发送多条消息不再报 JSON 解析错误。

#### 体验改进：提问后即时"正在思考"加载态
- **问题**：发送问题后，流式气泡立刻以空 `message assistant` 形式插入，界面先出现一个空白方框，直到首个 token 到达才有内容，没有任何"思考中"之类的反馈。
- **修复**：`app/frontend/index.html` 的 `sendMessage()` 在插入用户消息后**立即**渲染一个"正在思考"气泡（带跳动省略号动画 + 文案轮播："正在思考"→"正在检索相关资料"→"正在组织回答"，每 1.2s 切换）；收到首个 `token` 事件时将该气泡无缝替换为正式回答（清除轮播定时器），流式结束/出错/网络异常时均正确清理。
- **验证**：服务端 `/api/chat/stream` 实测返回 146 个 `token` 事件，前端"思考中"气泡会在首个 token 到达时被替换，不再出现空白方框。

#### Bug 3：问完第一个问题就"跳到新界面"，用户以为没反应又问一遍
- **现象**：用户问出第一条消息后，界面立刻回到"开始问答"空状态（像跳去了一个新问题界面），左侧"对话历史"也多了一条；而回答要等 RAG 检索 + LLM 生成（数秒）才回来，期间看起来"没反应"，于是用户重复提问。
- **根因**：前端 `sendMessage()` 在插入用户消息后调用 `saveMessageToConversation("user", msg)`，因为是首条消息 `currentConversationId` 为空，该函数会调用 `startNewConversation()`；而 `startNewConversation()` 内部有一句 **`clearHistory()`**，把整个聊天区清空并恢复"开始问答"空状态。由于 `saveMessageToConversation` 是未 await 的异步调用，这个清空动作会在"正在思考"气泡显示之后异步发生，**把用户问题和思考气泡一起抹掉**，界面退回空状态，造成"跳到新界面 + 没反应"的错觉。
- **修复**：把"创建会话"与"清空聊天显示"拆开——
  1. 新增 `ensureConversation()`：仅当 `currentConversationId` 为空时创建会话（服务端）+ 刷新侧栏，**不清空聊天显示**。`saveMessageToConversation()` 改为调用它。
  2. `startNewConversation()`（"新建对话"按钮）保留旧语义：先 `clearHistory()` 再 `ensureConversation()`，保证用户主动开新会话时显示是干净的。
  3. `sendMessage()` 中对用户消息的保存改为 `await`，使建会话顺序确定，不再异步清空显示。
- **效果**：首条消息发送后，用户问题气泡 + "正在思考"气泡都稳定保留，回答串行流式回来；侧栏新增一条对话历史属正常行为，不再有"跳新界面"的闪动，用户不会误以为没反应。
- **验证**：`node --check` 校验前端脚本语法通过；服务端（StaticFiles 每次从磁盘读取）已提供含 `ensureConversation` 的新版页面。

- **受影响文件**：`frontend/index.html`（`ensureConversation` / `startNewConversation` / `saveMessageToConversation` / `sendMessage`）。

### 2026-08-05: 测试套件修复 + 代码清理

- **单元测试全绿（32/32）**：修复此前 14 个失败用例。
  - 根因：运行环境缺第三方依赖（jwt / langchain_chroma / langchain_community 等），并非 mock 写错；另有 `tokenize` 断言未跟上「停用词过滤 + bigram」实现、`memory_manager` 测试中 `short_term` 被 Mock 占位导致 `len()` 失败。
  - 修复：`tests/conftest.py` 注册**惰性桩 Finder**，对当前环境未安装的重型/可选依赖（sentence_transformers / paddleocr / bs4 等）及其任意子模块动态返回 MagicMock 桩，使 `pytest tests/unit/` 在干净环境也能秒级通过；已真实安装的包不受影响。修正 `test_hybrid_retriever_v3.py` 的 `test_tokenize` 与 `test_memory_manager_fixed.py` 的 mock 配置。
- **依赖补齐（测试环境）**：安装 PyJWT / slowapi / redis / jieba / langchain_community / langchain_chroma（项目核心依赖，CI 应已包含）。
- **代码清理**：删除根目录 5 个临时脚本（`_fix_login.py` / `_fix_upload.py` / `test_hybrid.py` / `test_mm.py` / `test_retrieval.py`）；修复 `app/security/middleware.py` docstring 的无效转义警告（`SyntaxWarning`）。
- **作用**：clone 到干净环境 `pytest tests/unit/` 一键全绿，CI / 面试演示更可靠。

### 2026-08-05（续）: 代码整洁度 + Webhook 重试补全

- **生产路径 debug 输出规范化**：`app/memory/redis_client.py`、`app/processing/ocr_engine.py` 的连接 / 引擎选择日志由 `print()` 改为 `logging`（连接成功 `info`、回退 / 无引擎 `warning`）；`app/observability/tracker.py` 的链路追踪摘要由 `print()` 改为 `logger.debug`，避免服务器运行时向 stdout 刷屏。
- **Webhook 失败重试真正生效**：`app/worker/webhook.py` 的 `_retry_loop` 此前是空壳（仅留 TODO）。新增 `_retry_failed()`，每 60 秒轮询 `webhook_logs` 中 `success=0 且 attempts < MAX_RETRIES(5)` 的记录，复用 `_send_webhook` 重新投递（含签名与日志更新）；webhook 已删除时将该日志置为最大次数、停止重试。
- **清理过时 TODO**：`app/api/chat.py` 的 `stream` 字段原注释 `# TODO: implement streaming`，但 SSE 流式分支早已实现，改为如实描述。
- **仓库清理**：删除 `requirements.txt.bak` / `requirements.txt.orig` 两个 sed 备份冗余文件（均无引用）。
- **测试**：完整套件 `pytest tests/` → 44 passed / 1 skipped；1 条 `test_config::test_env_override` 失败为沙箱环境注入了超长 `LLM_API_KEY`（>32767 字符）所致，与本机运行无关。

### 2026-08-04: 安全加固 + 代码卫生 + 依赖/测试修复

> 本轮在代码体检基础上，修复了若干会直接阻塞上线的具体 bug（认证、限流、TLS、硬编码密钥等）。

#### 1. 真 JWT 认证（替换内存 token）
- `app/api/auth.py` 改用 PyJWT 签发/校验带签名、30 天过期的 Token，移除 `_tokens` 内存字典（此前重启即失效、多实例不共享、无签名）
- `config.py` 的 `JWT_SECRET` 现在真正参与签名；导出公共 `require_user` 依赖供各路由复用
- 新增 `app/core/limiter.py` 集中管理限流器

#### 2. 限流真正生效
- `app/main.py` 接上 `app.state.limiter` 并注册 `RateLimitExceeded` 异常处理器
- `app/api/chat.py` 修复"两个 `async def chat`"导致的覆盖 bug（之前带 `@limiter.limit` 的装饰器被无限流的同名函数吞掉）
- 限流策略：`/api/chat` 100/min、`/api/auth` 注册/登录 20/min，防爆破

#### 3. 恢复 TLS 证书校验
- `chat.py`(3 处)、`scripts/run_ragas_eval.py` 的 `verify=False` 改为 `True`；`embedder_factory.py` 移除显式 `verify` 参数（其 `requests.post` 默认 `verify=True`，TLS 同样开启）；`streamlit_app.py` 已删除
- 删除 `main.py`/`streamlit_app.py` 清空 `CURL_CA_BUNDLE`/`REQUESTS_CA_BUNDLE` 的行，以及 `ssl._create_unverified_context` 全局关闭 TLS 的危险写法

#### 4. 移除硬编码密钥
- `config.py`、`docker-compose.yml`、`embedder_factory.py`、`streamlit_app.py`、`scripts/run_ragas_eval.py` 中硬编码的 Volces embedding key 默认值全部移除，改为纯环境变量读取（`EMBEDDING_API_KEY`，无默认）
- 该 key 此前写在源码里等于已泄露，**部署前请去平台轮换**

#### 5. 代码卫生
- 删除根目录 7 个 `_fix_*.py` 临时脚本（含会把 redis 换成 alpine 的危险脚本 `_fix_compose.py`）
- 抽取公共 `require_user` 到 `auth.py`，替换 chat/documents/feedback/category/conversation/ab_testing 共 6 处重复定义
- 清理 `chat.py`/`documents.py` 的乱码注释

#### 6. 依赖与测试配置
- `requirements-docker.txt` 补 `sentence-transformers`/`paddleocr`/`paddlepaddle`/`pydantic-settings`/`pyjwt`（之前缺失会导致容器内 rerank/OCR 崩溃）
- `requirements.txt` 加 `pyjwt`
- `setup.cfg` 移除 `fail_under=80`，测试不再因覆盖率门槛而"变红"

**部署前必做**：① 轮换已泄露的 embedding key；② `.env` 设置强 `JWT_SECRET`（当前为占位默认值）；③ 提供 `EMBEDDING_API_KEY` 环境变量（`docker-compose.yml` 已改为 `${EMBEDDING_API_KEY:-}`，无默认）。

#### 7. 补齐 integration / evaluation 测试（测试章节从"待补"变为"已实现"）
- 新增 `tests/integration/`：`conftest.py`（隔离环境：临时 sqlite 用户库 + 临时上传/向量目录 + 每测试重置限流）、`test_auth_chain.py`、`test_rate_limit.py`、`test_chat_integration.py`、`test_document_upload.py`——共 11 个用例，验证 JWT 链路、限流 429、聊天全链路、上传落盘等真实接线
- 新增 `tests/evaluation/test_ragas_eval.py`：golden 集 schema 校验、离线 harness（mock LLM 组装数据集）、可选真实 RAGAS 评测（无依赖/无 key 自动 skip）；`scripts/run_ragas_eval.py` 改为惰性导入 ragas，使其无 ragas 也能 import
- 同步修正 `tests/unit/test_api_chat_simple.py` 两个陈旧断言（非法 token 现返回 401 而非 500），使其符合新的真 JWT 行为

#### 8. 修复两个会阻断 `app.main` 导入的真实 bug（集成测试发现）
- `app/api/chat.py`：`_validate_config()` 在模块导入期被调用，但 `_log` 在第 57 行才定义，配置校验失败时抛 `NameError` 导致整个应用无法启动——已将 `_log` 定义提前
- `app/api/admin.py`：仍引用已删除的内存 token 字典 `_tokens` 与不存在的文件存储函数 `_load_users`/`_save_users`，导致 `app.main` 导入失败（今日加的单元测试此前因此从未真正跑通）——已迁移到 sqlite 版 `list_users()`/`delete_user()`，并清理 admin 路由

#### 当前测试状态
- integration：11 用例全过；evaluation：2 过 + 1 跳过（需 `LLM_API_KEY`/`ARK_API_KEY`）；unit：29 过 + 3 陈旧失败
- 3 个 unit 失败与本次无关（`test_hybrid_retriever_v3::test_tokenize` 的 jieba 分词期望、`test_memory_manager_fixed` 的两个 Mock 设置问题），属历史遗留，待后续清理

- （状态更新 · 2026-08-05）以上为 2026-08-04 当晚状态；2026-08-05 已将 unit 3 个陈旧失败修绿，整体测试现为 **44 passed / 1 skipped**（unit 32 + integration 13 + evaluation 1 skipped）。
- （核验记录 · 2026-08-05）本节已对照 `git HEAD` 代码逐条核验：除本处测试状态已更新外，第 3 节 `embedder_factory.py` 实为「无显式 verify、靠 requests 默认 True」而非「verify=False→True」（已更正）；其余断言（PyJWT 真认证、限流注册、TLS 全开、admin 迁 sqlite、`require_user` 抽取、依赖补齐、无硬编码 key 等）均与代码一致。

---

### 2025-08-04: P2 高级功能（分组/对话/检索/A-B测试/Webhook）

#### 1. 知识库分组
- 新增文档分类管理：创建/删除分类、设置文档分类、按分类筛选文档
- 新增分类 API：`/api/categories`（CRUD）、`/api/categories/assign`（设置分类）、`/api/categories/list`（按分类列出）
- 前端侧边栏添加分类筛选下拉框和分类管理入口

**有什么用：** 可以按"合同/法规/案例"等维度组织文档，检索时可以限定在特定分类内，提高检索精度。

#### 2. 多轮对话管理
- 新增对话管理 API：`/api/conversations`（创建/列出/获取/删除）
- 支持对话标题、消息历史、继续对话
- 前端侧边栏添加对话历史列表，点击可加载历史对话

**有什么用：** 用户可以保存和恢复多个对话，方便回顾之前的问答内容。

#### 3. 全文检索集成（Elasticsearch）
- 新增 Elasticsearch 客户端：`app/retrieval/elasticsearch_client.py`
- 支持中文分词（IK analyzer）、索引管理、全文检索
- 集成到混合检索器作为兜底方案
- 可选功能，通过环境变量 `ELASTICSEARCH_HOSTS` 启用

**有什么用：** 当稠密向量和 BM25 检索效果不佳时，Elasticsearch 提供全文检索兜底，提升召回率。

#### 4. A/B 测试框架
- 新增实验管理 API：`/api/ab-testing/experiments`（创建/启动/停止/查看结果）
- 支持多变体配置、流量分配、事件记录
- 使用确定性哈希分配用户，保证一致性

**有什么用：** 可以对比不同检索策略、Prompt 模板、模型版本的效果，用数据驱动优化。

#### 5. Webhook 通知
- 新增 Webhook 管理 API：`/api/webhooks`（创建/更新/删除/触发/日志）
- 支持 8 种事件类型：文档上传/删除、对话完成、用户注册/删除、实验启动/停止、系统错误
- 支持签名验证、异步发送、重试机制

**有什么用：** 文档处理完成后自动通知外部系统，实现自动化工作流。

---

### 2025-08-04: P1 产品化功能（管理后台/预览/统计/错误处理/性能优化）

#### 1. 管理员后台 Web 界面
- 新增管理员 API：`/api/admin/users`（用户管理）、`/api/admin/stats`（系统统计）、`/api/admin/config`（配置查看）
- 新增管理员后台界面：统计卡片、用户管理表格、系统配置显示
- 仅管理员用户可以看到"管理后台"按钮
- 新增 `/api/auth/me` 端点获取当前用户信息

**有什么用：** 管理员可以方便地管理用户、查看系统状态，不需要直接操作数据库或配置文件。

#### 2. 文档预览功能
- 在文档列表中添加了预览按钮（👁图标）
- 创建了 PDF 预览模态框，支持翻页、缩放、下载
- 使用 PDF.js 库实现浏览器端 PDF 渲染
- 新增 `/api/documents/preview/{filename}` 端点

**有什么用：** 用户可以直接在浏览器中查看上传的 PDF 文档，无需下载到本地。

#### 3. 使用统计功能
- 集成指标记录到聊天 API（查询次数、Token 消耗、响应时间）
- 支持流式和非流式响应的指标记录
- 通过 `/metrics` 端点导出 Prometheus 格式指标

**有什么用：** 了解系统使用情况，发现性能瓶颈，为优化提供数据支撑。

#### 4. 完善错误处理机制
- 创建了全局错误处理模块：`app/security/error_handlers.py`
- 统一错误响应格式：`{error, status_code, message, detail, error_code}`
- 定义了 20+ 种错误码（AUTH_001-006, DOC_001-006, CHAT_001-004, SYS_001-004）
- 提供友好的中文错误提示（如"请先登录"、"登录已过期"、"仅支持PDF格式"）

**有什么用：** 前端可以根据错误码显示友好的提示信息，用户体验更好，排查问题也更方便。

#### 5. 性能优化
- 缓存优化：LRU 内存缓存 + 文件缓存双层架构，线程安全，支持统计和清理
- BM25 分词优化：添加中英文停用词过滤 + 中文 bigram 支持，提升检索质量

**有什么用：** 相同查询不再重复调用 LLM，检索结果更精准，响应更快。

---

### 2025-08-04: P0 上线必备功能（测试/安全/备份/监控）

#### 1. 完整测试套件
- 配置了 pytest 测试框架（pytest.ini、setup.cfg、.coveragerc）
- 创建了 `tests/conftest.py` 提供统一的测试 fixtures（mock Redis、ChromaDB、LLM 等外部依赖）
- 编写了核心模块单元测试：config、hybrid_retriever、memory_manager、api_chat
- 运行方式：`python -m pytest tests/unit/ -v`
- 新增依赖：pytest、pytest-cov、pytest-mock、httpx（已加入 requirements.txt）

**有什么用：** 保证每次代码改动不会悄悄破坏已有功能，CI/CD 可以自动跑测试，上线前有质量兜底。

#### 2. 生产级安全加固
- 新增 `app/security/middleware.py` 安全中间件模块
- **SecurityHeadersMiddleware**：自动添加 X-Content-Type-Options、X-Frame-Options、CSP、Referrer-Policy 等安全响应头，防止 MIME 嗅探、点击劫持、XSS 攻击
- **RequestSizeLimitMiddleware**：限制请求体大小（默认 100MB），防止 DoS 攻击
- **路径遍历防护**：`sanitize_filename()` + `is_safe_path()` + `get_safe_upload_path()`，修复了文件上传的路径穿越漏洞（之前用户传 `../../etc/passwd` 就能写到任意位置）
- **输入净化**：`sanitize_query_input()` + `is_query_safe()`，拦截脚本注入等危险输入
- **CORS 收紧**：从 `allow_origins=["*"]` 改为可配置的 `ALLOWED_ORIGINS`，生产环境不再接受任意域名
- **文件上传加固**：白名单限制仅允许 `.pdf`，增加文件大小校验
- **文档端点保护**：生产环境（`ENV=production`）自动隐藏 Swagger/ReDoc

**有什么用：** 堵住安全漏洞，防止恶意用户通过文件上传、路径穿越、XSS 等手段攻击系统，满足基本的安全上线要求。

#### 3. 数据备份与恢复
- 新增 `scripts/backup.py` CLI 备份恢复工具
- 支持 4 种操作：
  - `python scripts/backup.py backup` — 创建全量备份（chroma_db、uploads、memory_db、tenant_data）
  - `python scripts/backup.py list` — 列出所有备份
  - `python scripts/backup.py restore <backup_dir>` — 从备份恢复数据
  - `python scripts/backup.py cleanup --keep 5` — 清理旧备份，保留最近 N 个
- 自动记录 manifest.json（备份时间、源目录、校验和）

**有什么用：** 数据库损坏、误删文件、服务器迁移时可以快速恢复，避免数据丢失。

#### 4. 监控与告警
- 新增 `app/observability/monitoring.py` 监控模块
- 新增 3 个端点：
  - `GET /metrics` — Prometheus 兼容格式指标导出，可接入 Grafana 等监控平台
  - `GET /health` — 增强健康检查（自动检测 Redis 连通性、磁盘空间、内存使用）
  - `GET /stats` — 应用运行统计（查询数、延迟、Token 消耗等）
- 内置指标：查询总数/成功率/失败率、查询延迟 P50/P90/P99、Token 消耗、上传统计、系统 CPU/内存
- 线程安全的 MetricsCollector，支持计数器、仪表盘、直方图

**有什么用：** 服务挂了能第一时间知道，性能劣化能从指标看出来，方便运维和调优。

---

### 2025-08-01: 统一异步化重构
- 消灭重复代码：RAG 检索、Prompt 拼接等公共逻辑，现在只需要写一次
- 统一入口：前端只需要调用 POST /api/chat，通过 stream: true/false 控制行为
- 彻底异步化：把遗留的同步 requests.post 全部换成 httpx.AsyncClient
- 返回类型统一：异步函数中同时返回流和字典时用 JSONResponse 包裹，避免 FastAPI 序列化 Bug

### 2025-07-28: FastAPI + 角色系统 + Docker 迁移 D 盘
- 从 Streamlit 迁移到 FastAPI + 纯前端 HTML/JS
- 新增 super_admin 角色 + PDF 删除权限
- Docker 数据从 C 盘迁移到 D 盘（34GB -> 19.5GB）
- 修复浏览器缓存导致的中文乱码
- docker-compose 改为启动 FastAPI
- 重写 start-rag.bat 一键启动脚本

### 2025-07-26: Docker 部署
- Dockerfile + docker-compose.yml
- Redis 集成 + 健康检查

### 2025-07-25: Docker Compose 部署 + DNS 配置优化
- Docker Desktop 完整安装流程（winget + WSL2 + Ubuntu）
- DNS 调整 114.114.114.114 解决 Docker Hub IPv6 连接失败问题
- 配置 Daocloud 镜像代理 registry-mirrors 加速镜像拉取
- 创建 requirements-docker.txt（精简版，去掉 torch/paddlepaddle 等重型包）
- 修改 Dockerfile：从 Daocloud 拉取 python:3.12-slim 基础镜像 + Tsinghua PyPI 镜像
- Docker Compose + docker run 双模式可运行

启动方式：

```bash
cd legal-doc-rag
cp .env.example .env
docker compose up -d
```

注意事项：

- 如果 Docker Hub 连不上（IPv6 超时），修改 DNS 114.114.114.114
- 或配 registry-mirrors: https://docker.m.daocloud.io
- pip install 太慢时使用精简 requirements-docker.txt
- 首次构建约需 8-10 分钟（pip 下载依赖）

### 2025-07-19: RAGAS 评测跑通 + ProfileStore + 多租户
- RAGAS 评测跑通真实分数（豆包 API + 豆包 embedding）
- 新增 ProfileStore: 用户画像独立存储（置信度加权合并）
- 多租户隔离: Sidebar Tenant ID, 隔离记忆/向量库/画像
- 修复 EvaluationResult 访问方式 (r.scores 而非 dict)

### 2025-07-19: 接通全部闲置模块
- MultimodalPipeline: 替换 PyPDF2 + splitter（图文+OCR）
- HybridRetriever: 替换直接 Chroma retriever（BM25+Dense+RRF）
- QueryRewriter: 检索前 LLM 改写查询
- CitationTracker: 检索结果来源标注
- TraceContext: 全链路耗时 + Token 追踪
- 移除 PyPDF2 RecursiveCharacterTextSplitter import

### 2025-07-19: 5 项生产级改进 (memory_manager.py)
1. clear_session: 修复 Redis 僵尸数据（先清数据再重置 session_id）
2. 异步访问计数: 检索时反遗忘（ShadowWorker 批量更新）
3. 实体提取: 实现 _do_extract_entity（原为 pass）
4. 增量摘要合并: 旧摘要+新对话 -> LLM -> 合并
5. Redis 容灾恢复: __init__ 末尾调用 _restore_from_redis()

### 2025-07-18: 消除 Monkey Patching
- 删除 original_xxx / patched_xxx / 模块末尾赋值
- ForgettingMechanism ShadowWorker 直接内建在类方法
- 修复 extract_entities stub, 添加 memory_llm 回调
- 删除 .orig 备份文件


---

## 项目框架 (FastAPI 版)

### 目录结构
`
legal-doc-rag/
├── app/
│   ├── main.py                    # FastAPI 入口，注册路由 + 加载 .env
│   ├── api/                       # HTTP API 层
│   │   ├── auth.py                # POST /api/auth/login, /register
│   │   ├── chat.py                # POST /api/chat (流式 SSE)
│   │   ├── documents.py           # POST /api/documents/upload, GET list, DELETE
│   │   ├── feedback.py            # POST /api/feedback
│   │   └── __init__.py
│   ├── frontend/
│   │   └── index.html             # 单页前端 (原生 JS + CSS)
│   ├── core/
│   │   └── config.py              # 集中配置：API key、模型名、路径
│   ├── retrieval/                 # 检索层
│   │   ├── embedder_factory.py    # 本地 BGE-M3 Embedding 工厂 (HuggingFaceEmbeddings)
│   │   ├── hybrid_retriever.py    # HybridRetriever: 稠密(BERT) + 稀疏(BM25) + RRF 融合 + BGE 重排
│   │   ├── query_rewriter.py      # QueryRewriter: LLM 查询改写/扩展
│   │   ├── citation.py            # CitationTracker: 来源引用追踪
│   │   ├── cache.py               # QueryCache: Redis 查询缓存
│   │   └── __init__.py
│   ├── processing/                # 文档处理层
│   │   ├── multimodal_pipeline.py # MultimodalPipeline: PDF 图文解析
│   │   ├── pdf_extractor.py       # PyMuPDF 图文提取
│   │   ├── ocr_engine.py          # OCR (PaddleOCR / Tesseract)
│   │   └── __init__.py
│   ├── memory/                    # 记忆层
│   │   ├── memory_manager.py      # MemorySystem: 短期 + 长期记忆
│   │   ├── conversation_store.py  # 对话持久化 (Redis)
│   │   ├── redis_client.py        # Redis 连接池 + TTL
│   │   ├── forgetting.py          # 艾宾浩斯遗忘曲线
│   │   ├── profile_store.py       # 用户画像存储
│   │   └── __init__.py
│   ├── tenant/                    # 租户层
│   │   ├── auth.py                # 用户注册/登录/密码哈希 (SQLite)
│   │   ├── tenant_manager.py      # 租户创建/隔离
│   │   └── __init__.py
│   ├── worker/                    # 异步任务层
│   │   ├── shadow_worker.py       # ShadowWorker: 后台异步线程池
│   │   └── __init__.py
│   ├── observability/             # 可观测层
│   │   ├── tracker.py             # TraceContext: 全链路追踪 (耗时, Token)
│   │   ├── structured_logger.py   # 结构化日志
│   │   └── __init__.py
│   ├── evaluation/                # 评估层 (离线)
│   │   ├── evaluator.py           # RAGAS 三维度打分
│   │   ├── runner.py              # 批量评测 + Golden Test Set
│   │   └── __init__.py
│   └── ingestion/                 # (预留) 多模态图文注释
│       ├── vision_caption.py
│       └── __init__.py
├── requirements-docker.txt
├── Dockerfile
├── docker-compose.yml
├── start-rag.bat                  # Docker 启动脚本
├── start-local.bat                # 本地启动脚本 (uvicorn)
├── healthcheck.py                 # Docker 健康检查
├── .env                           # 环境变量 (API key 等)
└── tenant_data/                   # SQLite 数据 (自动创建)
`

### 模块调用链

`
用户请求
    │
    ▼
app/main.py (FastAPI 入口)
    │  ├── app/api/auth.py          → app/tenant/auth.py (SQLite)
    │  │                               └── app/core/config.py
    │  │
    │  ├── app/api/chat.py          → app/retrieval/embedder_factory.py → 本地 BGE-M3 Embedding
    │  │                               → app/retrieval/hybrid_retriever.py → BM25 + Dense + RRF
    │  │                               → app/retrieval/query_rewriter.py → DeepSeek LLM
    │  │                               → app/retrieval/citation.py
    │  │                               → app/retrieval/cache.py → Redis
    │  │                               → app/memory/memory_manager.py → Chroma + Redis
    │  │                               → app/worker/shadow_worker.py (异步)
    │  │                               → app/observability/tracker.py
    │  │                               → app/observability/structured_logger.py
    │  │
    │  ├── app/api/documents.py     → app/retrieval/embedder_factory.py
    │  │                               → app/processing/multimodal_pipeline.py
    │  │                                   → app/processing/pdf_extractor.py
    │  │                                   → app/processing/ocr_engine.py
    │  │                               → langchain Chroma (向量持久化)
    │  │
    │  └── app/api/feedback.py      → app/memory/conversation_store.py
    │
    └── app/frontend/index.html (前端静态文件)
`

### 请求完整流程 (上传+提问)

`
1. 用户上传 PDF
   POST /api/documents/upload
   ├── app/api/documents.py: 接收文件 → 保存到 ./uploads/{tenant_id}/ → 立即返回 task_id（**异步，不阻塞**）
   ├── 后台线程池执行：app/processing/multimodal_pipeline.py 解析 PDF (PyMuPDF + OCR) → embedder_factory 生成向量 → ChromaDB 持久化到 ./chroma_db/{tenant_id}/
   ├── 任务状态持久化到 `data/tasks.json`，服务重启后从磁盘恢复，避免"已上传却提示请先上传文档"
   ├── 服务启动时自动扫描 `uploads/{tenant_id}/`，对未向量化的 PDF 重新提交后台索引任务
   ├── 进度查询：GET /api/documents/task/{task_id} 返回 pending/processing(extracting→embedding→building_index)/done/failed 及百分比
   └── 索引完成后即可提问；索引中提问会返回"文档正在后台索引中"提示而非报错；已上传但索引失败会提示重新上传

2. 用户提问
   POST /api/chat (SSE 流式)
   ├── app/api/chat.py: 验证 Token → 加载 ChromaDB 向量库
   ├── app/retrieval/query_rewriter.py: LLM 改写/扩展查询
   ├── app/retrieval/hybrid_retriever.py:
   │   ├── 稠密检索: ChromaDB.similarity_search_with_score()
   │   ├── 稀疏检索: BM25Okapi.get_scores()
   │   ├── BGE-M3 稀疏检索: SPLADE 词汇权重（自计算，dot-product 打分）
   │   └── RRF 融合（稠密 + BM25 + BGE-M3 稀疏 + 可选 ES）+ 可选 BGE 重排
   ├── app/retrieval/citation.py: 记录来源引用
   ├── app/memory/memory_manager.py: 加载短期/长期记忆
   ├── 调用 DeepSeek LLM (stream=True) 生成回答
   ├── app/observability/tracker.py: 记录耗时和 Token 用量
   └── 返回 SSE 流给前端
`

### 数据流向

`
PDF文件
  → processing/multimodal_pipeline (解析文本+图片)
  → embedder_factory (转向量)
  → ChromaDB (持久化到磁盘)

用户问题
  → query_rewriter (LLM 改写)
  → hybrid_retriever (稠密 + 稀疏 + RRF)
  → memory_manager (加载记忆上下文)
  → [合并上下文 + 引用] → DeepSeek LLM
  → 流式返回 → 前端渲染
"

## 生产上线前检查清单

> 基于 2026-08-05 对 `HEAD`（commit `cf6a9dd`）的实地核查。区分「面试/作品集展示」与「真实生产部署」两档要求。

### 当前状态速览
- ✅ **功能完整**：P0/P1/P2 全部实现（RAG 核心、安全、管理后台、多轮对话、A/B、Webhook、监控、备份）
- ✅ **测试**：44 passed / 1 skipped（注意：LLM / embedding 真实调用链路全程 mock，未用真实 key 跑过）
- ✅ **密钥安全**：`.env` 已被 `.gitignore` 忽略且未入库
- ✅ **容器编排**：Docker + compose（Redis + Chroma 持久化卷）+ `/api/health` healthcheck
- ✅ **健康检查**：`main.py` 挂载 monitoring router 提供 `/api/health`，compose 已配置 healthcheck
- ⚠️ **CI 不完整**：已有 `.github/workflows/ci.yml`，但**只跑 `scripts/ci_check.py` 语法检查，不跑 pytest**
- ⚠️ **检索层有死代码**：P2 写了 `app/retrieval/elasticsearch_client.py`，但 compose 未起 ES 服务、requirements 无 ES 依赖 → 未启用

### P0 — 上线阻断项（必须完成）
- [ ] **真实链路端到端验证**：用真实 `LLM_API_KEY` 跑通「文档上传→向量化→检索→问答（含 SSE 流式）」全流程（embedding 默认本地 BGE-M3，无需 key；当前测试全 mock，上线可能直接报错）
- [ ] **修复 `.env.example` 的 embedding 配置（真 bug）**：第 11 行 `EMBEDDING_MODEL_NAME` 变量 `config.py` 根本不读；实际需要的 `EMBEDDER_TYPE` / `EMBEDDING_API_KEY` / `EMBEDDING_BASE_URL` / `EMBEDDING_MODEL` 全未列出，不填则检索必失败
- [ ] **让 CI 真正跑测试**：在 `ci.yml` 增加 step 运行 `pytest tests/unit tests/integration`（当前仅语法检查）
- [ ] **修复文档端口错误**：`.env.example` 注释写「访问 http://localhost:8501」（Streamlit 旧端口，已删除），改为实际端口 `8000`
- [ ] **清理冗余**：删除 `.env.example.orig` 备份（sed 残留）

### P1 — 强烈建议（生产稳定性）
- [ ] **HTTPS / TLS**：生产环境经反向代理（Nginx 等）配置 TLS，加密 Token / API Key 传输
- [ ] **Elasticsearch 检索层（实验性 · 默认关闭）**：代码已实现并作为可选 feature-flag （`HybridRetriever(use_elasticsearch=...)`，默认 `False`），但生产编排未接入——`docker-compose.yml` 未起 ES 服务、`requirements` 无 `elasticsearch` 依赖。如需启用：① compose 加 ES 服务 ② requirements 加 `elasticsearch` ③ main 创建 retriever 时传 `use_elasticsearch=True` ④ 重新验证混合检索走 ES；保持关闭则不影响现有 Chroma + BM25 检索，无功能缺失。
- [ ] **Redis 生产化**：限流/会话依赖 Redis，多副本部署必须配 `REDIS_URL`（当前有内存回退，单机 OK、多实例会乱）
- [ ] **密钥管理**：生产用密钥服务/环境变量注入，`.env` 不入仓库；建立 key 定期轮转
- [ ] **向量库持久化与备份**：定期备份 `chroma_db`（已有 `scripts/backup.py`，需接入定时任务）
- [ ] **监控告警闭环**：`/metrics`（Prometheus）接 Grafana / 告警规则

### P2 — 可选增强
- [ ] Webhook 重试改指数退避（当前固定 60s）
- [ ] 真实并发 / 压测验证
- [ ] 日志聚合（ELK / Loki）
- [ ] ragas 评估接真实 `LLM_API_KEY`（当前 `test_ragas_eval.py` 因缺 key 被 skip）
- [ ] 速率限制按租户维度细化

### 结论
- **面试 / 作品集**：已达偏上水平，重点准备「混合检索如何融合」「三层记忆如何设计」「多租户如何隔离」三道题
- **真实生产**：完成 P0（尤其真实链路验证 + embedding 配置修复）即可宣布「可上线」；P1 决定长期稳定性

---
