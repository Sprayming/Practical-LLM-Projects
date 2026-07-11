# 法律文书 RAG 系统（Legal Document RAG）

基于 LangChain + Streamlit 的法律文书智能问答系统。上传合同、法规等 PDF 文档后，可以用自然语言提问，系统自动检索相关条款并生成带引用的回答。

---

## 系统架构

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          用户界面 (Streamlit)                                │
│  ┌──────────┐  ┌──────────────────────────────────────────────────────────┐ │
│  │  侧边栏   │  │                    聊天区域                               │ │
│  │  - 上传PDF │  │  - 对话历史显示                                          │ │
│  │  - Token统计│  │  - 输入框 + 发送                                         │ │
│  │  - 记忆状态 │  │  - 引用来源展开                                          │ │
│  └──────────┘  └──────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
┌─────────────────────────────────────┴─────────────────────────────────────┐
│                           处理管道 (Python)                                 │
│                                                                           │
│  用户输入 ──→ 检索文档 ──→ 构建记忆上下文 ──→ 调用 LLM ──→ 返回回答           │
│                    │                │              │                       │
│                    ▼                ▼              ▼                       │
│              ChromaDB 向量库   三层记忆系统    DeepSeek API                 │
│              (法律条文)        (短/中/长+画像)                              │
│                                                                           │
└─────────────────────────────────────────────────────────────────────────────┘
```

## 核心架构：三层记忆系统

```
用户对话
  │
  ├── 短期记忆（最近3轮原文，~600 token）
  │     └── 保留对话语境连贯性
  │
  ├── 中期记忆（LLM 压缩摘要，~200 token）
  │     └── 保留关键事实和法条引用编号
  │
  ├── 长期记忆（ChromaDB 向量检索）
  │     └── 按语义检索相关历史对话（top-k）
  │
  └── 🆕 实体画像（结构化 JSON，~100 token）
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
| 短期记忆（3轮） | ~600 | 动态截断 |
| 实体画像 | ~100 | JSON 结构化 |
| 长期记忆（检索） | ~500 | top-k 相似度 |
| 检索文档 | ~2000 | top-5 chunk，去重 |
| 用户输入 | <500 | 截断保护 |
| **总计** | **~3800** | 预留回复空间 |

## 目录结构

```
legal-doc-rag/
├── app/
│   ├── streamlit_app.py           # 主入口（Streamlit UI + 处理管道）
│   ├── memory/
│   │   ├── __init__.py
│   │   └── memory_manager.py      # 三层记忆系统
│   ├── config.py                   # 配置
│   ├── models.py                   # 数据模型
│   ├── main.py                     # FastAPI 入口（备用）
│   ├── api/                        # FastAPI 路由
│   ├── generation/                 # LLM 调用
│   ├── ingestion/                   # 文档加载 + 切分
│   └── retrieval/                  # 向量存储 + 检索
├── frontend/                       # HTML 前端（备用）
├── data/                           # 上传文档
├── chroma_db/                      # 文档向量库
├── memory_db/                      # 记忆向量库
├── model_cache/                    # 嵌入模型缓存
├── profile.json                    # 用户画像数据
└── .env                            # API Key
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置 API Key

```bash
cp .env.example .env
# 编辑 .env，填入 LLM_API_KEY
```

### 3. 启动（Streamlit 版）

```bash
cd legal-doc-rag
streamlit run app/streamlit_app.py
```

浏览器打开 `http://localhost:8501`

### 4. 使用

1. 上传法律 PDF 文档
2. 等待嵌入模型加载（首次约10秒）
3. 在输入框提问
4. 查看带引用来源的 AI 回答

## 技术栈

| 组件 | 选型 |
|------|------|
| 前端框架 | Streamlit |
| 向量数据库 | ChromaDB（文档 + 记忆） |
| 嵌入模型 | text2vec-base-chinese（HuggingFace） |
| LLM | DeepSeek API |
| 记忆系统 | 自研三层（短/中/长 + 画像） |
| 文档解析 | PyPDF2 |
| 文本切分 | LangChain RecursiveCharacterTextSplitter |
| 实体提取 | LLM 影子调用 |
| 数据持久化 | JSON + ChromaDB |

## API 接口（备用 FastAPI 模式）

### POST /api/documents/upload
上传法律文档

### POST /api/chat/
提问

### GET /health
健康检查

## 项目状态

- ✅ 基础 RAG 问答
- ✅ 三层记忆系统
- ✅ 实体画像提取
- ✅ Token 统计
- ✅ P0/P1 防御性编程
- 🚧 异步影子 Worker
- 🚧 多租户隔离
- 🚧 遗忘机制
