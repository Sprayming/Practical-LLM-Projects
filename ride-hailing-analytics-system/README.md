# Ride-Hailing Analytics System
网约车平台的数据分析运营系统

基于自然语言查询的数据分析系统，面向网约车运营场景。
用户可以用日常语言问"哪个价位的卡券核销率最高？"，系统自动生成 SQL、查询数据库、分析数据并给出运营建议。

**项目类型**：NL2SQL + 数据分析 Agent（基于 LLM 的智能数据分析平台）

## 系统架构

### 整体架构图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              用户层 (User Layer)                            │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │   Web UI    │  │   REST API  │  │   CLI       │  │   SDK       │        │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘        │
└─────────┼────────────────┼────────────────┼────────────────┼────────────────┘
          │                │                │                │
          ▼                ▼                ▼                ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            网关层 (Gateway Layer)                           │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  CORS │ 速率限制 │ 请求验证 │ SQL注入检测 │ 安全头 │ 监控中间件    │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           应用层 (Application Layer)                        │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                         FastAPI Application                         │   │
│  ├─────────────┬─────────────┬─────────────┬─────────────┬─────────────┤   │
│  │  Query API  │ Dashboard   │ History API │  Auth API   │ Monitor API │   │
│  └──────┬──────┴──────┬──────┴──────┬──────┴──────┬──────┴──────┬──────┘   │
│         │             │             │             │             │          │
│         ▼             ▼             ▼             ▼             ▼          │
│  ┌─────────────┐ ┌─────────┐ ┌───────────┐ ┌───────────┐ ┌───────────┐   │
│  │   NLSQL     │ │Dashboard│ │  History  │ │   Auth    │ │ Monitoring│   │
│  │  Module     │ │ Module  │ │  Module   │ │  Module   │ │  Module   │   │
│  └──────┬──────┘ └────┬────┘ └─────┬─────┘ └─────┬─────┘ └─────┬─────┘   │
└─────────┼─────────────┼────────────┼─────────────┼─────────────┼──────────┘
          │             │            │             │             │
          ▼             ▼            ▼             ▼             ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           核心层 (Core Layer)                               │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                        Agent Orchestrator                           │   │
│  │  ┌─────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────┐ │   │
│  │  │ Planner │───▶│  SQL Tool   │───▶│Analysis Tool│───▶│Report   │ │   │
│  │  │         │    │             │    │             │    │Tool     │ │   │
│  │  └─────────┘    └─────────────┘    └─────────────┘    └─────────┘ │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐          │
│  │  SQL Gen    │ │  SQL Exec   │ │ Interpreter │ │ Recommender │          │
│  │  (LLM)     │ │  (Validator)│ │  (LLM)      │ │  (LLM)      │          │
│  └──────┬──────┘ └──────┬──────┘ └──────┬──────┘ └──────┬──────┘          │
└─────────┼───────────────┼───────────────┼───────────────┼──────────────────┘
          │               │               │               │
          ▼               ▼               ▼               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          基础设施层 (Infrastructure Layer)                   │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐          │
│  │   Cache     │ │   Database  │ │   LLM API   │ │   Tasks     │          │
│  │  (Memory)   │ │ (SQLite/MySQL│ │ (DeepSeek)  │ │ (Background)│          │
│  └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘          │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 核心流程

```
用户问题
  │
  ▼
[输入验证] ──▶ [净化 & 安全检查]
  │
  ▼
[Planner] ──▶ LLM 拆解问题为执行步骤
  │
  ▼
[SQL Generator] ──▶ LLM 根据 Schema 生成 SQL
  │
  ▼
[SQL Validator] ──▶ 安全校验（只允许 SELECT）
  │
  ▼
[SQL Executor] ──▶ 执行查询，返回数据
  │
  ▼
[Interpreter] ──▶ LLM 解读数据，生成洞察
  │
  ▼
[Recommender] ──▶ LLM 生成运营建议
  │
  ▼
返回结果（摘要 + 洞察 + 建议 + SQL + 数据）
```

### 技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| **前端** | HTML/CSS/JS + Chart.js | 响应式Web界面，4种图表 |
| **后端** | FastAPI + Uvicorn | 高性能异步Python Web框架 |
| **AI引擎** | DeepSeek LLM | 可替换为OpenAI/本地模型 |
| **数据库** | SQLite (开发) / MySQL (生产) | 双数据库支持 |
| **缓存** | 内存缓存 (LRU + TTL) | 查询结果缓存，10分钟过期 |
| **监控** | Prometheus + Grafana | 指标采集 + 可视化仪表盘 |
| **认证** | JWT + API Key | 双认证方式 |
| **部署** | Docker + Nginx | 容器化部署，反向代理 |

## 系统特性

### 核心功能
- **自然语言查询**：用日常语言提问，自动生成SQL并分析数据
- **智能分析**：LLM驱动的数据解读和业务洞察
- **运营建议**：基于数据的可执行运营策略
- **可视化仪表盘**：直观的数据展示和图表

### 生产级特性
- **监控告警**：Prometheus指标采集 + Grafana仪表盘 + 慢请求日志
- **查询历史**：自动保存查询记录，支持搜索、收藏、分页
- **数据导出**：支持CSV和JSON格式导出
- **性能优化**：查询缓存、异步任务、内存LRU淘汰
- **安全防护**：JWT认证、SQL注入防护、速率限制、输入验证

## 数据模型

- **drivers** — 司机信息（ID、姓名、手机号、注册时间等）
- **coupon_types** — 卡券类型（面值、有效期、使用条件等）
- **coupons** — 卡券发放记录（用户、面值、状态、发放时间等）
- **orders** — 订单记录（司机、乘客、金额、时间等）
- **redemptions** — 核销记录（卡券、订单、核销时间等）

## 快速开始

### 方式一：本地开发

1. **环境准备**
   ```bash
   # 克隆项目
   git clone <repository-url>
   cd ride-hailing-analytics-system
   
   # 创建虚拟环境
   python -m venv venv
   source venv/bin/activate  # Windows: venv\Scripts\activate
   
   # 安装依赖
   pip install -r requirements.txt
   ```

2. **配置环境**
   ```bash
   # 复制环境配置文件
   cp .env.example .env
   
   # 编辑 .env 文件，填入必要配置
   # - LLM_API_KEY: DeepSeek API密钥
   # - DB_HOST: 数据库地址（默认127.0.0.1）
   # - DB_NAME: 数据库名（默认ride_hailing）
   ```

3. **初始化数据库**
   ```bash
   # 创建数据库表
   python scripts/init_db.py
   ```

4. **启动服务**
   ```bash
   # 启动开发服务器
   python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
   
   # 访问应用
   # - Web界面: http://127.0.0.1:8001
   # - API文档: http://127.0.0.1:8001/docs
   # - ReDoc文档: http://127.0.0.1:8001/redoc
   ```

### 方式二：Docker部署

1. **环境准备**
   ```bash
   # 确保已安装Docker和Docker Compose
   docker --version
   docker-compose --version
   ```

2. **配置环境**
   ```bash
   cp .env.example .env
   # 编辑 .env 文件，填入LLM_API_KEY
   ```

3. **启动服务**
   ```bash
   # 构建并启动所有服务
   docker-compose up -d
   
   # 查看日志
   docker-compose logs -f
   
   # 停止服务
   docker-compose down
   ```

## API文档

### 认证API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/auth/register | 用户注册 |
| POST | /api/auth/login | 用户登录 |
| GET | /api/auth/me | 获取当前用户信息 |
| POST | /api/auth/api-key | 创建API密钥 |
| POST | /api/auth/change-password | 修改密码 |

### 数据分析API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/query/ | 自然语言查询 |
| GET | /api/dashboard/ | 仪表盘数据 |

### 查询历史API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/history/ | 创建查询历史 |
| GET | /api/history/ | 列出查询历史（分页/搜索） |
| GET | /api/history/stats | 查询统计 |
| GET | /api/history/{id} | 获取单条历史 |
| PUT | /api/history/{id}/favorite | 切换收藏状态 |
| DELETE | /api/history/{id} | 删除历史 |
| GET | /api/history/export/{format} | 导出（csv/json） |

### 监控API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/monitoring/metrics | Prometheus指标 |
| GET | /api/monitoring/health | 健康检查 |
| GET | /api/monitoring/stats | 应用统计 |

### 任务API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/tasks/ | 列出任务 |
| GET | /api/tasks/{id} | 获取任务状态 |
| DELETE | /api/tasks/{id} | 取消任务 |
| POST | /api/tasks/cleanup | 清理过期任务 |

### 查询示例

```bash
# 自然语言查询
curl -X POST "http://127.0.0.1:8001/api/query/" \
  -H "Content-Type: application/json" \
  -d '{"question": "哪个价位的卡券核销率最高？"}'

# 带认证的查询
curl -X POST "http://127.0.0.1:8001/api/query/" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <your-token>" \
  -d '{"question": "最近30天哪个司机的订单量最多？"}'
```

## 项目结构

```
ride-hailing-analytics-system/
├── app/                          # 应用代码
│   ├── api/                     # API路由层
│   │   ├── auth.py              # 认证API（注册/登录/API密钥）
│   │   ├── dashboard.py         # 仪表盘API
│   │   ├── history.py           # 查询历史API（CRUD/导出）
│   │   ├── query.py             # 核心查询API
│   │   └── tasks.py             # 异步任务API
│   ├── auth/                    # 认证模块
│   │   ├── database.py          # 用户数据库（SQLite）
│   │   ├── dependencies.py      # FastAPI依赖注入
│   │   ├── jwt_handler.py       # JWT令牌管理
│   │   └── models.py            # 用户模型
│   ├── cache/                   # 缓存模块
│   │   └── redis_cache.py       # 内存缓存（LRU + TTL）
│   ├── history/                 # 查询历史模块
│   │   ├── database.py          # 历史数据库
│   │   └── models.py            # 历史模型
│   ├── monitoring/              # 监控模块
│   │   ├── metrics.py           # Prometheus指标
│   │   └── middleware.py        # 监控中间件
│   ├── security/                # 安全模块
│   │   ├── error_handlers.py    # 统一错误处理
│   │   ├── middleware.py         # 安全中间件
│   │   └── validators.py        # 输入验证
│   ├── nlsql/                   # 自然语言转SQL
│   │   ├── schema_parser.py     # 数据库Schema解析
│   │   ├── sql_executor.py      # SQL执行与校验
│   │   └── sql_generator.py     # LLM生成SQL
│   ├── analysis/                # 数据分析
│   │   ├── interpreter.py       # LLM数据解读
│   │   └── recommender.py       # LLM运营建议
│   ├── agent/                   # Agent编排
│   │   ├── orchestrator.py      # 任务调度器
│   │   ├── planner.py           # LLM问题拆解
│   │   └── tools/               # 工具集
│   ├── tasks/                   # 异步任务
│   │   └── background.py        # 后台任务管理
│   ├── db/                      # 数据库连接
│   │   └── connection.py        # SQLite连接管理
│   ├── static/                  # 静态文件
│   │   └── index.html           # 前端界面（四Tab布局）
│   ├── config.py                # 应用配置
│   ├── models.py                # Pydantic数据模型
│   └── main.py                  # 应用入口
├── data/                        # 数据文件
│   ├── schema.sql               # MySQL表结构
│   ├── schema_sqlite.sql        # SQLite表结构
│   └── *.db                     # SQLite数据库文件
├── monitoring/                  # 监控配置
│   ├── prometheus.yml           # Prometheus配置
│   └── grafana/                 # Grafana配置
│       ├── datasources.yml      # 数据源配置
│       ├── dashboards.yml       # 仪表盘配置
│       └── dashboards/          # 仪表盘JSON
├── scripts/                     # 脚本工具
│   └── init_db.py               # 数据库初始化
├── tests/                       # 测试代码（44个测试）
│   ├── conftest.py              # pytest fixtures
│   ├── test_api.py              # API测试
│   ├── test_config.py           # 配置测试
│   ├── test_models.py           # 模型测试
│   ├── test_nlsql.py            # SQL生成测试
│   └── test_security.py         # 安全测试
├── Dockerfile                   # Docker镜像配置
├── docker-compose.yml           # Docker Compose（5服务）
├── nginx.conf                   # Nginx反向代理配置
├── pytest.ini                   # pytest配置
├── requirements.txt             # Python依赖
├── .env.example                 # 环境变量模板
└── README.md                    # 项目文档
```

### Docker 服务架构

```yaml
services:
  app:        # FastAPI应用 (端口 8001)
  db:         # MySQL 8.0 (端口 3306)
  nginx:      # 反向代理 (端口 80)
  prometheus: # 指标采集 (端口 9090)
  grafana:    # 监控仪表盘 (端口 3000)
```

## 测试

项目包含 **44 个测试用例**，覆盖核心模块：

| 测试文件 | 测试数 | 覆盖模块 |
|----------|--------|----------|
| test_config.py | 3 | 配置加载、环境变量、验证 |
| test_models.py | 10 | Pydantic数据模型 |
| test_nlsql.py | 15 | SQL生成、Schema解析、SQL安全校验 |
| test_api.py | 7 | API接口（mock测试） |
| test_security.py | 9 | SQL注入攻击、输入验证 |

```bash
# 运行所有测试
pytest

# 运行指定模块测试
pytest tests/test_nlsql.py -v

# 运行带覆盖率的测试
pytest --cov=app --cov-report=html

# 查看测试报告
# 打开 htmlcov/index.html
```

## 配置说明

### 环境变量

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| DB_HOST | 数据库地址 | 127.0.0.1 |
| DB_PORT | 数据库端口 | 3306 |
| DB_NAME | 数据库名 | ride_hailing |
| DB_USER | 数据库用户 | root |
| DB_PASSWORD | 数据库密码 | |
| LLM_API_KEY | LLM API密钥 | |
| LLM_BASE_URL | LLM API地址 | https://api.deepseek.com/v1 |
| LLM_MODEL | LLM模型名 | deepseek-chat |
| LLM_TEMPERATURE | 生成温度 | 0.05 |
| DEBUG | 调试模式 | true |

### LLM配置

系统支持多种LLM提供商，只需修改以下配置：
- **DeepSeek**: `LLM_BASE_URL=https://api.deepseek.com/v1`
- **OpenAI**: `LLM_BASE_URL=https://api.openai.com/v1`
- **本地模型**: `LLM_BASE_URL=http://localhost:11434/v1`

## 开发指南

### 添加新功能

1. 在 `app/` 下创建新模块
2. 在 `app/api/` 中添加路由
3. 在 `app/main.py` 中注册路由
4. 编写测试用例
5. 更新文档

### 代码规范

- 遵循 PEP 8 代码风格
- 使用类型注解
- 编写文档字符串
- 添加单元测试

## 常见问题

### 1. 数据库连接失败
- 检查数据库服务是否启动
- 确认 `.env` 中的数据库配置
- 确保数据库已创建并导入schema

### 2. LLM API调用失败
- 检查API密钥是否正确
- 确认网络连接正常
- 检查API额度是否充足

### 3. 端口被占用
```bash
# 查找占用端口的进程
netstat -ano | findstr :8001

# 终止进程
taskkill /PID <进程ID> /F
```

## 项目演进

本项目从原型到生产级应用，经历了三个版本迭代：

```
v0.1.0 (原型) ──▶ v0.2.0 (准生产) ──▶ v0.3.0 (生产级)
     │                   │                    │
     │                   │                    │
     ▼                   ▼                    ▼
  基础功能           P0+P1改进              P2改进
  · NL2SQL          · 测试 (44个)          · 监控告警
  · 数据分析         · 安全加固             · 查询历史
  · Agent编排        · 用户认证             · 数据导出
                    · Docker部署           · 可视化增强
                    · 前端界面             · 性能优化
                    · API文档
```

### 版本对比

| 特性 | v0.1.0 | v0.2.0 | v0.3.0 |
|------|--------|--------|--------|
| **核心查询** | ✅ | ✅ | ✅ |
| **Agent编排** | ✅ | ✅ | ✅ |
| **测试** | ❌ | ✅ 44个 | ✅ 44个 |
| **安全中间件** | ❌ | ✅ 4个 | ✅ 4个 |
| **用户认证** | ❌ | ✅ JWT | ✅ JWT |
| **Docker** | ❌ | ✅ 3服务 | ✅ 5服务 |
| **前端界面** | 基础 | 响应式 | 四Tab |
| **监控** | ❌ | ❌ | ✅ Prometheus |
| **查询历史** | ❌ | ❌ | ✅ |
| **数据导出** | ❌ | ❌ | ✅ CSV/JSON |
| **缓存** | ❌ | ❌ | ✅ LRU |
| **异步任务** | ❌ | ❌ | ✅ |
| **API端点** | 2个 | 8个 | 20+个 |

### 改进优先级说明

项目采用 P0/P1/P2 三级优先级进行改进：

- **P0（必须）**：测试、安全、错误处理 — 直接影响生产可用性
- **P1（重要）**：认证、文档、部署、前端 — 影响用户体验和运维
- **P2（优化）**：监控、历史、可视化、性能 — 提升系统质量和效率

## 更新日志

### v0.3.0 (2026-08-05) — 生产级增强

在 v0.2.0 基础上新增监控、历史、可视化、性能优化四大模块。

#### 📊 监控告警（P2）
- 新增 `app/monitoring/metrics.py` — Prometheus 指标采集：
  - 请求计数器/延迟直方图（`app_requests_total`, `app_request_latency_seconds`）
  - SQL 查询计数器/延迟（`app_sql_queries_total`, `app_sql_query_latency_seconds`）
  - LLM 调用计数器/延迟/Token 用量（`app_llm_calls_total`, `app_llm_tokens_total`）
  - 系统资源指标（CPU / 内存 / 磁盘使用率）
  - 健康检查端点（`/api/monitoring/health`）+ 应用统计端点（`/api/monitoring/stats`）
- 新增 `app/monitoring/middleware.py` — 监控中间件 + 慢请求日志（>2s 告警）
- 新增 `monitoring/prometheus.yml` — Prometheus 采集配置
- 新增 `monitoring/grafana/` — Grafana 数据源 + 仪表盘自动配置
- 更新 `docker-compose.yml` — 新增 Prometheus（9090）+ Grafana（3000）服务

#### 📋 查询历史 & 数据导出（P2）
- 新增 `app/history/` 查询历史模块：
  - `models.py` — QueryHistory / QueryHistoryCreate / ExportFormat 模型
  - `database.py` — SQLite 查询历史表 + CRUD 操作 + 统计接口
- 新增 `app/api/history.py` — 7 个 API：
  - 创建/列表/详情/收藏切换/删除查询历史
  - 查询统计端点（总查询数/成功率/平均延迟/今日查询数）
  - CSV / JSON 数据导出（支持指定记录、元数据开关）

#### 📈 数据可视化增强（P2）
- 重写 `app/static/index.html` — 四 Tab 布局：
  - **仪表盘** — 统计卡片（带趋势指标）+ 今日查询趋势图 + 状态分布图
  - **智能查询** — 保留原有查询功能
  - **数据图表** — 4 种图表：卡券面值饼图、核销趋势折线图、订单金额柱状图、司机活跃度雷达图
  - **查询历史** — 历史列表 + 搜索 + 收藏 + 分页 + CSV/JSON 导出按钮
  - Tab 切换、防抖搜索、移动端适配

#### ⚡ 性能优化（P2）
- 新增 `app/cache/redis_cache.py` — 内存缓存实现：
  - LRU 淘汰策略 + TTL 过期
  - 查询结果缓存（`QueryCache`）— 默认 10 分钟过期，最大 500 条
  - 缓存命中率统计
  - `@cached_query` 装饰器
- 新增 `app/tasks/background.py` — 异步任务管理器：
  - `TaskManager` — 任务提交/状态查询/列表/清理
  - `TaskStatus` 枚举（pending / running / completed / failed）
  - 示例任务（长时间查询、数据导出、缓存预热）
- 新增 `app/api/tasks.py` — 任务 API：列出/查询/取消/清理任务

### v0.2.0 (2026-08-04) — 从原型到准生产

从原型/Demo级别提升到接近生产可用，共新增 50+ 文件，44 个测试全部通过。

#### 🧪 测试（P0）
- 配置 pytest 框架（`pytest.ini` + `conftest.py`）
- 新增 44 个测试用例，覆盖 5 个模块：
  - `tests/test_config.py` — 配置加载与环境变量（3 个）
  - `tests/test_models.py` — Pydantic 数据模型验证（10 个）
  - `tests/test_nlsql.py` — SQL 生成、Schema 解析、SQL 安全校验（15 个）
  - `tests/test_api.py` — API 接口 mock 测试（7 个）
  - `tests/test_security.py` — SQL 注入攻击模拟、输入验证（9 个）

#### 🔒 安全（P0）
- 新增 `app/security/middleware.py` — 4 个安全中间件：
  - `SecurityHeadersMiddleware` — X-Content-Type-Options, CSP 等安全响应头
  - `RequestSizeLimitMiddleware` — 请求体大小限制（1MB）
  - `RateLimitMiddleware` — 基于 IP 的速率限制（60 次/分钟）
  - `SQLInjectionMiddleware` — 危险 SQL 模式检测
- 新增 `app/security/validators.py` — 输入净化、文件名校验、SQL 注入检测、API 密钥格式验证
- 新增 `app/security/error_handlers.py` — 统一错误处理框架：
  - `AppError` 基类 + 5 个子类（ValidationError, NotFoundError, DatabaseError, LLMError, SecurityError）
  - 全局异常处理器（AppError / HTTPException / Exception）

#### 🛡️ 错误处理（P0）
- 重写 `app/api/query.py` — 分层异常处理（输入验证 → SQL生成 → SQL执行 → 数据分析 → 建议生成）
- 重写 `app/main.py` — 注册安全中间件 + 错误处理器 + 应用生命周期管理

#### 👤 用户认证（P1）
- 新增 `app/auth/` 认证模块：
  - `models.py` — UserCreate, UserLogin, Token, PasswordChange 等 Pydantic 模型
  - `database.py` — SQLite 用户表 + API 密钥表 + 密码哈希（SHA256+盐）
  - `jwt_handler.py` — JWT 令牌创建/验证
  - `dependencies.py` — FastAPI 依赖注入（get_current_user, get_current_admin_user 等）
- 新增 `app/api/auth.py` — 5 个认证 API：注册、登录、用户信息、创建 API 密钥、修改密码

#### 📖 API 文档（P1）
- 配置 Swagger UI（`/docs`）和 ReDoc（`/redoc`）
- 所有 API 端点添加中文说明和标签

#### 🐳 Docker 部署（P1）
- 新增 `Dockerfile` — Python 3.11 基础镜像 + uvicorn
- 新增 `docker-compose.yml` — 三服务架构：
  - `app` — FastAPI 应用（端口 8001）
  - `db` — MySQL 8.0（端口 3306）+ schema 自动初始化
  - `nginx` — 反向代理（端口 80）+ 安全头 + 请求限制
- 新增 `nginx.conf` — 反向代理配置
- 新增 `.dockerignore` — 构建排除规则

#### 🎨 前端数据可视化（P1）
- 新增 `app/static/index.html` — 完整响应式 Web 界面：
  - 仪表盘卡片（总卡券数 / 核销数 / 核销率）
  - 智能查询输入框（支持回车提交）
  - Chart.js 图表（卡券面值饼图 + 核销趋势折线图）
  - 查询结果展示（摘要 / 洞察 / 建议 / SQL / 数据表格）
  - 移动端适配

#### 📝 文档
- 重写 `README.md`：
  - 系统特性 / 技术架构 / 安全特性
  - 快速开始（本地开发 + Docker 部署）
  - 完整 API 文档（认证 API + 数据分析 API）
  - 项目结构 / 测试说明 / 配置说明 / 开发指南 / 常见问题

### v0.1.0 (2026-07-20)
- 🎉 初始版本发布
- ✅ 基础自然语言查询功能（DeepSeek LLM）
- ✅ SQL 自动生成与安全校验
- ✅ 数据分析与运营建议
- ✅ Agent 编排（Planner → SQLTool → AnalysisTool → ReportTool）
- ✅ 仪表盘 API

## 贡献指南

1. Fork 项目
2. 创建功能分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 创建 Pull Request

## 许可证

MIT License - 详见 [LICENSE](LICENSE) 文件
