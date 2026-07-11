# 法律文书 RAG 系统（Legal Document RAG）

基于 LangChain + Streamlit 的法律文书智能问答系统。上传合同、法规等 PDF 文档后，可以用自然语言提问，系统自动检索相关条款并生成带引用的回答。

---

## 为什么分了这么多文件？

对比 `05_综合案例.md`（单文件）和本项目（多文件）：

| | 综合案例（单文件） | 本项目（多文件） |
|--|-----------------|----------------|
| 设计目的 | 教学演示，一眼看完完整流程 | 可扩展的生产级架构 |
| VolcEngineEmbeddings | 嵌入逻辑嵌在主文件里 | 抽到 `utils/embeddings.py` |
| 记忆系统 | 无 | 独立模块 `memory/`（200+行） |
| DeepSeek 调用 | 手写 requests | 抽到 `generation/llm.py` |
| 配置 | 硬编码在 `global_var` | `config.py` + `.env` |
| PDF 解析 | 写在主文件里 | 抽到 `ingestion/loader.py` |
| 切分逻辑 | 写在主文件里 | 抽到 `ingestion/chunker.py` |

**核心原则**：单文件适合教学，多文件适合迭代。当记忆系统超过 200 行时，不拆开根本没法维护。

---

## 框架总览

```
用户操作（浏览器）
     │
     ▼
streamlit_app.py（主入口）
     │
     ├── 页面渲染（sidebar + 聊天区）
     ├── PDF 上传处理
     │      ├── loader.py（解析 PDF → 纯文本）
     │      └── chunker.py（按条款切分）
     │
     ├── 问答处理
     │      ├── 文档检索（ChromaDB）
     │      │      ├── embeddings.py（HuggingFace 模型）
     │      │      └── vector_store.py（向量库操作）
     │      ├── 记忆系统（memory_manager.py）
     │      │      ├── 短期记忆 raw text
     │      │      ├── 中期记忆摘要
     │      │      ├── 长期记忆向量库
     │      │      └── 实体画像 profile.json
     │      └── LLM 调用（generation/llm.py）
     │
     └── 后台影子提取
            └── memory.extract_entities() → profile.json
```

---

## 文件关系图

```
streamlit_app.py          ← 主入口，所有逻辑从这里发起的
  │
  ├── app/memory/memory_manager.py   ← 三层记忆系统（本项目独有的设计）
  │     ├── ChromaDB（记忆向量库）
  │     └── profile.json（用户画像）
  │
  ├── app/utils/embeddings.py        ← HF_ENDPOINT 配置 + HuggingFace 嵌入
  │
  ├── app/ingestion/
  │     ├── loader.py                 ← PDF/DOCX/TXT 文本提取
  │     └── chunker.py               ← 按条款优先的文本切分
  │
  ├── app/retrieval/
  │     └── vector_store.py           ← ChromaDB 向量存储操作
  │
  └── app/generation/
        └── llm.py                    ← ChatOpenAI 配置 + QA 链（LangChain 版）
                ↓
            DeepSeek API

其他文件（FastAPI 支架，当前未在 Streamlit 中使用）：
  ├── app/config.py          ← 配置中心
  ├── app/models.py          ← 数据模型
  ├── app/main.py            ← FastAPI 入口
  ├── app/api/chat.py        ← 聊天 API
  └── app/api/documents.py   ← 文档上传 API
```

---

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
| 嵌入模型 | text2vec-base-chinese | `utils/embeddings.py` |
| 文档向量库 | ChromaDB | `retrieval/vector_store.py` |
| 记忆向量库 | ChromaDB | `memory/memory_manager.py` |
| 用户画像 | JSON 文件 | `memory/memory_manager.py` |
| LLM | DeepSeek API | `generation/llm.py` |
| PDF 解析 | PyPDF2 | `ingestion/loader.py` |
| 文本切分 | RecursiveCharacterTextSplitter | `ingestion/chunker.py` |

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
