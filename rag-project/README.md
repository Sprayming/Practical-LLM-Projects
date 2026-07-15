# RAG Enterprise — 企业级知识库问答系统

基于检索增强生成（Retrieval-Augmented Generation）的企业级智能知识库问答系统。

## 架构总览

```
                        ┌─────────────────┐
                        │   浏览器/客户端   │
                        │  (HTML / API)    │
                        └────────┬────────┘
                                 │ HTTP / JSON
                                 ▼
┌─────────────────────────────────────────────────┐
│              FastAPI Backend (:8000)              │
│                                                   │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐        │
│  │  文档管线  │  │  检索模块  │  │  生成模块  │        │
│  │ Load→Chunk│→│ Embed→Search│→│ Context→LLM│       │
│  └──────────┘  └────┬─────┘  └──────────┘        │
│                      │                            │
│               ┌──────▼──────┐                     │
│               │   ChromaDB   │                     │
│               │  (向量存储)   │                     │
│               └─────────────┘                     │
└─────────────────────────────────────────────────┘
```

## 项目结构

```
rag-project/
├── .github/
│   ├── workflows/ci.yml       # GitHub Actions CI
│   └── ISSUE_TEMPLATE/         # Bug / Feature 模板
├── backend/                    # Python 后端
│   ├── app/
│   │   ├── api/               # API 路由层
│   │   ├── ingestion/         # 文档加载 + 分块管线
│   │   ├── retrieval/         # 嵌入 + 向量检索
│   │   ├── generation/        # LLM 提示词 + 生成
│   │   ├── config.py          # 配置管理
│   │   ├── models.py          # Pydantic 模型
│   │   └── main.py            # FastAPI 入口
│   ├── tests/                 # 测试套件
│   ├── uploads/               # 上传文件暂存
│   ├── chroma_db/             # ChromaDB 持久化
│   ├── Dockerfile
│   ├── requirements.txt
│   └── pyproject.toml         # 项目元数据 + 工具配置
├── frontend/
│   └── index.html             # 单页前端（零构建）
├── scripts/
│   ├── setup.ps1              # 环境初始化
│   ├── dev.ps1                # 启动开发服务器
│   ├── lint.ps1               # 代码检查
│   └── test.ps1               # 测试运行
├── docker-compose.yml         # 容器化部署
├── .pre-commit-config.yaml    # Git 钩子
└── .gitignore
```

## 快速开始

前提：Python 3.11+，DeepSeek API Key。

```powershell
# 1. 初始化环境
.\scripts\setup.ps1

# 2. 配置 API Key
#    编辑 backend\.env，填入 DEEPSEEK_API_KEY 或 LLM_API_KEY

# 3. 启动后端
.\scripts\dev.ps1

# 4. 打开前端
#    浏览器打开 frontend\index.html
```

后端启动后访问：
- API: `http://127.0.0.1:8000`
- Swagger 文档: `http://127.0.0.1:8000/docs`

## 技术栈

| 组件 | 选型 | 选型理由 |
|------|------|----------|
| 后端框架 | FastAPI | 类型安全、异步原生、自动文档 |
| 向量存储 | ChromaDB | 本地持久化、零外部依赖、生产可用 |
| 嵌入模型 | 本地 jieba + n-gram 哈希（768维） | 零外部依赖，离线运行 |
| 生成模型 | deepseek-chat | 或 deepseek-reasoner |
| 文档解析 | PyMuPDF / python-docx | 高精度 PDF/Word 解析 |
| 分块策略 | Token 感知滑动窗口 | 精确控制上下文窗口 |
| 代码检查 | ruff + mypy | 快速、严格的 Python 工具链 |
| 前端 | 单 HTML 文件 | 零构建依赖，快速迭代 |
| 部署 | Docker Compose | 一键容器化 |

## 开发工作流

```
feature branch → 本地开发 → lint → test → PR → CI → merge to main
```

推荐分支策略：`git flow` 风格。

```
develop  ──────────────►  main  (发布)
   │                        │
   ├ feature/xxx            │
   ├ bugfix/xxx             │
   └── 合并后删除分支         │
```

## 测试规范

测试文件放在 `backend/tests/`，命名 `test_*.py`。

```powershell
# 运行所有测试
.\scripts\test.ps1

# 带覆盖率报告
.\scripts\test.ps1 -Coverage

# 只运行特定标记
.\scripts\test.ps1 -Marker "unit"
```

## 代码规范

- Python 3.11+ 类型注解
- ruff 格式化（双引号、100 字符行宽）
- mypy 严格模式类型检查
- pre-commit 自动检查

```powershell
# 手动运行 lint
.\scripts\lint.ps1
```

## Docker 部署

```powershell
# 构建并启动
docker compose up -d

# 查看日志
docker compose logs -f
```

## 路线图

- [ ] RAG 核心管线（Load → Chunk → Embed → Store → Retrieve → Generate）
- [ ] 文档上传 / 管理 / 删除 API
- [ ] 带引用问答 API
- [ ] 前端管理界面
- [ ] 混合检索（BM25 + 向量）
- [ ] Cross-encoder Reranker
- [ ] 多轮对话上下文
- [ ] 多租户权限隔离
- [ ] 私有化部署（Docker Compose）
- [ ] 监控 + 日志聚合
