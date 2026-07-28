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
| POST | /api/documents/upload | 上传 PDF | Bearer |
| GET | /api/documents | 文档列表 | Bearer |
| DELETE | /api/documents/{filename} | 删除文档（超管） | Bearer |
| POST | /api/chat | RAG 问答 | Bearer |
| GET | /api/health | 健康检查 | 无 |

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

## 更新日志

### 2026-07-28: FastAPI + 角色系统 + Docker 迁移 D 盘
- 从 Streamlit 迁移到 FastAPI + 纯前端 HTML/JS
- 新增 super_admin 角色 + PDF 删除权限
- Docker 数据从 C 盘迁移到 D 盘（34GB -> 19.5GB）
- 修复浏览器缓存导致的中文乱码
- docker-compose 改为启动 FastAPI
- 重写 start-rag.bat 一键启动脚本

### 2026-07-26: Docker 部署
- Dockerfile + docker-compose.yml
- Redis 集成 + 健康检查

### 2026-07-19: RAGAS + 多租户
- RAGAS 三维度离线评测
- SQLite 用户管理 + 多租户隔离