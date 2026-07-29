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
### 44. 修复 DirectEmbed 传错导致检索崩溃 (2026-07-29)
改动: app/api/chat.py
根因: HybridRetriever 的 dense_store 参数期望 ChromaDB（有 similarity_search_with_score 方法），
但代码传了 embedder（DirectEmbed 对象，只有 embed_query 方法），导致 AttributeError。
修复: HybridRetriever(embedder, all_texts, k=10) → HybridRetriever(vector_store, all_texts, k=10)

### 45. FastAPI 版文件 GBK 编码问题 (2026-07-29)
改动: app/api/*.py
根因: 另一台电脑用 GBK (Windows 默认编码) 写了 Python 文件，Python 3 默认用 UTF-8 解析时崩溃。
同时 .env 文件被 .gitignore 排除，导致容器内 load_dotenv() 读取不到，embedding 配置全走默认值。
修复:
  - 将 GBK 编码的文件转为 UTF-8
  - docker-compose.yml 补全 EMBEDDING_API_KEY / EMBEDDING_BASE_URL / EMBEDDING_MODEL 环境变量
  - 修复 .env 缺失导致 embedding 指向 DeepSeek 而非火山引擎的问题
