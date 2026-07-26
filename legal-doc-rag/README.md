# Legal Document RAG

生产级法律文书智能问答系统。上传 PDF 合同、法规、法律文件，用自然语言提问，
系统自动检索相关条款并生成带引用的回答。

---

## 项目架构

```
streamlit_app.py          ← 唯一入口（UI + 对话流编排）
  │
  ├── memory/              三层记忆系统
  │   ├── memory_manager.py   短/中/长期记忆 + 实体画像
  │   ├── redis_client.py     Redis 连接 + TTL 过期 + 内存回退
  │   ├── forgetting.py       艾宾浩斯遗忘曲线
  │   └── shadow_worker.py    异步后台线程池
  │
  ├── processing/          文档处理
  │   └── multimodal_pipeline.py  PDF 图文提取（文字 + OCR + 图片描述）
  │
  ├── retrieval/           检索层
  │   ├── embedder_factory.py   可插拔 Embedder 工厂
  │   ├── hybrid_retriever.py   BM25 + Dense + RRF
  │   ├── query_rewriter.py     LLM 查询改写/扩展
  │   ├── citation.py           来源引用追踪
  │   └── cache.py              查询缓存
  │
  ├── observability/       可观测性
  │   ├── tracker.py            全链路追踪（耗时、Token）
  │   └── structured_logger.py  结构化日志
  │
  ├── tenant/              多租户（基础）
  └── evaluation/          离线评测（RAGAS）
```

---

## 核心设计决策与踩坑记录

### 1. DeepSeek 模型名变更

**问题：** DeepSeek 直接废弃了 `deepseek-chat` 模型名，API 返回 400。

**修复：** 代码中所有 `"deepseek-chat"` 替换为 `os.getenv("LLM_MODEL", "deepseek-v4-pro")`。

```python
# 之前（线上必挂）
"model": "deepseek-chat"

# 之后（双层保护）
"model": os.getenv("LLM_MODEL", "deepseek-v4-pro")
```

**.env 配置：**
```ini
LLM_MODEL=deepseek-v4-pro
# 可选项：deepseek-v4-flash（更快更便宜）
```

**面试价值：** 模型名硬编码等于埋雷。API 厂商随时可能下架旧模型名，
环境变量 + fallback 默认值是生产基本操作。

---

### 2. Embedder Factory：可插拔嵌入层

**问题：** 原代码使用 `langchain-openai` 的 `OpenAIEmbeddings`，内部用 `tiktoken`
将文本转为 token ID 整数再发送，但豆包 Embedding API 只接受原始文本字符串，
导致 `400 BadRequest`。

**修复：** 自研 `DirectEmbed` 类，直接 HTTP 请求发送原始文本。

```python
class DirectEmbed:
    def embed_documents(self, texts):
        # 直接发 text 字符串，不经过 tokenizer
        resp = requests.post(f"{base_url}/embeddings", json={
            "model": self.model, "input": texts
        })
        return [item["embedding"] for item in resp.json()["data"]]
```

**工厂模式：**
```python
# .env 里写一行，切换 embedder
EMBEDDER_TYPE=openai        # 生产：豆包 API（零 GPU，秒级启动）
EMBEDDER_TYPE=huggingface   # 本地开发：HuggingFace（零成本，离线可用）
```

**为什么不用 OpenAIEmbeddings：**

| 方案 | 发送内容 | 豆包兼容 | 结果 |
|------|---------|---------|------|
| `OpenAIEmbeddings` | token ID 列表（整数） | ❌ | 400 BadRequest |
| `DirectEmbed` | 原始文本字符串 | ✅ | 200 OK |

**面试价值：**
> 我问了为什么要自研 Embedder 而不是用框架现成的。答：
> LangChain 的 OpenAIEmbeddings 为了性能会预 tokenizer 文本，但豆包 API
> 只收字符串不收 token ID。我用工厂模式封装了一层，生产用 API、
> 本地切 HuggingFace，改 `.env` 一个字段就行。

---

### 3. 三层记忆系统 + 实体画像

```
短期记忆（最近 6 轮原话）     ← 内存 + Redis List (TTL 2h)
  │ 超过 6 轮触发整理
  ▼
中期记忆（LLM 增量摘要）     ← 内存 + Redis String (TTL 24h)
  │ ShadowWorker 异步执行
  ▼
长期记忆（ChromaDB 向量库）  ← 永久存储 + 遗忘曲线
  │
  ▼
实体画像（异步提取）         ← LLM 提取 JSON 实体存入向量库
```

**遗忘机制：** 艾宾浩斯曲线 + 访问即激活。
记忆分数 `score = 0.5 × 近因 + 0.3 × 频率 + 0.2 × 重要性`，低于阈值自动过滤。

---

### 4. Token 预算分配

| 层级 | 预算 | 说明 |
|------|------|------|
| System Prompt | ~100 | 固定不变 |
| 短期记忆（原文） | ~600 | 最近 6 轮 |
| 中期记忆（摘要） | ~200 | LLM 增量合并 |
| 长期记忆（检索） | ~500 | 向量检索 Top-K |
| 引用上下文 | ~1500 | 检索到的文档片段 |
| 用户问题 | ~200 | 当前轮次输入 |
| 回答输出 | ~800 | 生成结果 |
| **总计/轮** | **~3900** | |

---

### 5. 常见的缺失导入（已修复）

在开发过程中发现多处类/函数定义在模块中但未被导入：

```
TraceContext       → from app.observability.tracker
get_trace_store    → from app.observability.tracker
QueryRewriter      → from app.retrieval.query_rewriter
CitationTracker    → from app.retrieval.citation
MultimodalPipeline → from app.processing.multimodal_pipeline
MemorySystem       → from app.memory.memory_manager
```

---

## 快速启动

### Docker（推荐）

```bash
# 1. 确保 Docker Desktop 运行
# 2. 构建镜像（首次需要）
docker build -t legal-doc-rag_app:latest .

# 3. 启动 Redis + App
docker run -d --name legal-doc-rag-redis-1 -p 6379:6379 alpine:3.18 \
  sh -c "apk add --no-cache redis && redis-server --bind 0.0.0.0"

docker run -d --name legal-doc-rag-app-1 -p 8501:8501 \
  --link legal-doc-rag-redis-1:redis \
  -e REDIS_URL="redis://redis:6379/0" \
  -e LLM_API_KEY="sk-xxxx" \
  -e LLM_BASE_URL="https://api.deepseek.com/v1" \
  -e EMBEDDING_API_KEY="df9c..." \
  -e EMBEDDING_BASE_URL="https://ark.cn-beijing.volces.com/api/v3" \
  -e EMBEDDING_MODEL="ep-m-xxxx" \
  -e EMBEDDER_TYPE="openai" \
  legal-doc-rag_app:latest

# 4. 打开浏览器
open http://localhost:8501
```

### 本地开发（不依赖 Docker）

```bash
pip install -r requirements-docker.txt
streamlit run app/streamlit_app.py
```

---

## 面试核心问题清单

### Q1：Embedding 为什么不用本地模型而用 API？
**答：** Embedder 是可切换的。生产用 API（零 GPU、Docker 镜像 <1GB、冷启动 3 秒），
本地开发切 `EMBEDDER_TYPE=huggingface` 不改代码。这是策略模式在 embedding 层的落地。

### Q2：Token 成本怎么控制？
**答：** 分层记忆设计。长文本压缩成摘要（200 token），最近对话保持原文（600 token），
长期记忆按语义检索。embedding API 在整个 RAG 成本中占比 <5%，LLM 推理才是大头。

### Q3：模型名变了怎么办？
**答：** 通过环境变量控制模型名，代码里给 fallback。DeepSeek 停掉 `deepseek-chat` 后，
改一行 `.env` 就切到 `deepseek-v4-pro`，零代码变更。

### Q4：检索不到相关内容怎么办？
**答：** 混合检索（BM25 + 稠密向量 + RRF）兜底，前端 LLM 查询改写扩展用户问题。
如果仍无结果，返回"未找到"而非硬编答案，降低幻觉风险。

### Q5：这个项目和企业级 RAG 差距在哪？
**答：** 目前是单租户、单知识域。企业级需要多租户隔离、RBAC 权限、API 限流、
A/B 评测流水线、监控告警。代码架构支持横向扩展，但生产环境还需要
至少再加 3-4 个模块（鉴权、限流、监控、CI/CD）。

---

## 环境变量说明

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `LLM_API_KEY` | - | DeepSeek API 密钥 |
| `LLM_BASE_URL` | `https://api.deepseek.com/v1` | API 地址 |
| `LLM_MODEL` | `deepseek-v4-pro` | 模型名 |
| `EMBEDDER_TYPE` | `openai` | openai / huggingface |
| `EMBEDDING_API_KEY` | - | 豆包 API 密钥 |
| `EMBEDDING_BASE_URL` | `https://ark.cn-beijing.volces.com/api/v3` | Embedding API 地址 |
| `EMBEDDING_MODEL` | `ep-m-xxxx` | Embedding 模型 ID |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis 连接 |
| `APP_PASSWORD` | - | 可选的访问密码 |