# Dental RAG System

牙科知识库智能问答系统 — 基于 RAG（检索增强生成）架构。

## 项目结构

```
dental-rag-system/
├── app/                    # FastAPI 后端
│   ├── main.py            # 应用入口
│   ├── config.py          # 配置中心
│   ├── models.py          # 数据模型
│   ├── api/
│   │   ├── chat.py        # 问答 API
│   │   └── documents.py   # 文档管理 API
│   ├── generation/
│   │   ├── llm.py         # LLM 调用
│   │   └── prompt_templates.py
│   ├── ingestion/
│   │   ├── loader.py      # 文档加载
│   │   └── chunker.py     # 文本切分
│   └── retrieval/
│       ├── embedder.py    # 嵌入
│       ├── vector_store.py # 向量存储
│       └── retriever.py   # 检索器
├── frontend.html           # 前端页面
├── .env.example            # 环境变量模板
├── requirements.txt        # Python 依赖
└── README.md
```

## 快速开始

### 1. 配置

复制 `.env.example` 为 `.env`，填入你的 DeepSeek API Key：

```bash
cp .env.example .env
# 编辑 .env，填入 LLM_API_KEY
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 启动

```bash
# PowerShell
python run.py

# 或者直接
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### 4. 使用

浏览器打开 `frontend.html`，上传牙科知识文档，即可开始问答。

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/documents/upload | 上传文档 |
| GET  | /api/documents/ | 文档列表 |
| DELETE | /api/documents/{id} | 删除文档 |
| POST | /api/chat/ | 问答 |
| GET  | /health | 健康检查 |

## 技术栈

- FastAPI + Uvicorn
- ChromaDB（向量数据库）
- DeepSeek API（LLM）
- jieba + n-gram hash（本地嵌入）
- tiktoken（token 计数）
