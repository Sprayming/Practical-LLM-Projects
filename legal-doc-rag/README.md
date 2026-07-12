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
