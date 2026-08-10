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

### 核心流程（多Agent协作）

```
┌─────────────────────────────────────────────────────────────────┐
│                          用户问题                               │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Orchestrator (协调者Agent)                    │
│         分析任务 → 制定计划 → 分配任务 → 整合结果               │
└─────────────────────────────┬───────────────────────────────────┘
                              │
          ┌───────────────────┼───────────────────┐
          │                   │                   │
          ▼                   ▼                   ▼
┌───────────────────┐ ┌───────────────────┐ ┌───────────────────┐
│    SQL Agent      │ │  Analysis Agent   │ │   Report Agent    │
│ · 理解业务问题    │ │ · 选择分析方法    │ │ · 确定报告重点    │
│ · 生成SQL查询     │ │ · 执行数据分析    │ │ · 生成运营建议    │
│ · 优化查询性能    │ │ · 发现业务洞察    │ │ · 格式化输出      │
│ · 自主决策采样    │ │ · 评估数据质量    │ │ · 优先级排序      │
└─────────┬─────────┘ └─────────┬─────────┘ └─────────┬─────────┘
          │                     │                     │
          └─────────────────────┼─────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Shared Memory (共享记忆)                    │
│                    上下文同步 · 状态共享 · 消息传递              │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│              返回结果（摘要 + 洞察 + 建议 + SQL + 数据）         │
└─────────────────────────────────────────────────────────────────┘
```

### 技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| **前端** | HTML/CSS/JS + Chart.js | 响应式Web界面，4种图表 |
| **后端** | FastAPI + Uvicorn | 高性能异步Python Web框架 |
| **AI引擎** | DeepSeek LLM | 可替换为OpenAI/本地模型 |
| **Agent框架** | 多Agent协作 | 4个Agent自主决策、消息传递、共享记忆 |
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

### 业务功能
- **真实数据模拟**：模拟网约车运营数据（司机/订单/卡券/核销）
- **运营报告生成**：自动生成周报/月报（核心指标+趋势分析+运营建议）
- **异常检测告警**：自动识别订单/金额/核销率异常并告警

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

### 运营报告API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/report/generate | 生成运营报告（week/month） |
| GET | /api/report/metrics | 获取核心指标 |
| GET | /api/report/trend | 获取趋势数据 |
| GET | /api/report/coupon-analysis | 卡券分析 |
| GET | /api/report/top-drivers | TOP司机排名 |
| GET | /api/report/hourly-distribution | 时段分布 |

### 异常检测API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/anomaly/detect | 检测所有异常 |
| GET | /api/anomaly/summary | 异常摘要 |
| GET | /api/anomaly/health | 系统健康检查 |

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
│   │   ├── tasks.py             # 异步任务API
│   │   ├── report.py            # 运营报告API
│   │   └── anomaly.py           # 异常检测API
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
│   ├── report/                  # 运营报告模块
│   │   └── generator.py         # 报告生成器
│   ├── anomaly/                 # 异常检测模块
│   │   └── detector.py          # 异常检测器
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
│   ├── agent/                   # 多Agent协作框架
│   │   ├── base.py              # Agent基类、共享记忆、消息传递
│   │   ├── agents.py            # 专业Agent（SQL/Analysis/Report）
│   │   ├── orchestrator.py      # 多Agent协调器
│   │   ├── planner.py           # LLM问题拆解（兼容）
│   │   └── tools/               # 工具集（兼容）
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
│   ├── init_db.py               # 数据库初始化
│   └── generate_data.py         # 数据模拟生成器
├── eval/                        # 评测体系
│   └── nl2sql/                  # NL2SQL 评测集
│       ├── evaluation_set.json  # 22条中文问题 + gold SQL + 期望断言
│       └── run_eval.py          # 评测脚本（gold校验 / --with-llm 真实准确率）
├── tests/                       # 测试代码（66个测试）
│   ├── conftest.py              # pytest fixtures
│   ├── test_api.py              # API测试
│   ├── test_config.py           # 配置测试
│   ├── test_models.py           # 模型测试
│   ├── test_nlsql.py            # SQL生成测试
│   ├── test_nl2sql_eval.py      # NL2SQL评测集集成测试（22条）
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

项目包含 **66 个测试用例**，覆盖核心模块：

| 测试文件 | 测试数 | 覆盖模块 |
|----------|--------|----------|
| test_config.py | 3 | 配置加载、环境变量、验证 |
| test_models.py | 10 | Pydantic数据模型 |
| test_nlsql.py | 15 | SQL生成、Schema解析、SQL安全校验 |
| test_api.py | 7 | API接口（mock测试） |
| test_security.py | 9 | SQL注入攻击、输入验证 |
| test_nl2sql_eval.py | 22 | NL2SQL评测集（真实DB端到端执行） |

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

> 注意：`test_api.py` / `test_nlsql.py` 等使用 mock 数据库，**测试全绿不等于系统真的能跑**（详见「踩坑记录与复盘」坑 2）。
> `test_nl2sql_eval.py` 是唯一走**真实 SQLite 库**端到端执行的测试，专门用来兜住 schema 契约漂移。

## NL2SQL 评测集

Text-to-SQL 系统最容易被追问的一句话是：**"你的准确率是多少？"**
本项目用一套可复现的评测集把这个问题量化，而不是靠"感觉还行"。

### 评测集设计

`eval/nl2sql/evaluation_set.json` 共 **22 条**中文业务问题，每条包含：

- `question`：运营口吻的自然语言问题（如"上周哪个城市的完成订单最多？"）
- `gold_sql`：人工编写的标准答案 SQL，严格对齐 `data/schema_sqlite.sql` 真实列名
- `expect`：结果形态断言（期望列名、行数区间、是否非空等），用于自动判分

题型分布（刻意覆盖 NL2SQL 的典型难度阶梯）：

| 类别 | 条数 | 说明 |
|------|------|------|
| single_table_aggregation | 4 | 单表聚合：COUNT / SUM / AVG |
| filtering | 4 | 条件过滤：状态、金额、枚举值 |
| join | 4 | 多表 JOIN：订单×司机、卡券×券种×核销 |
| time_filter | 2 | 时间过滤：近 7 天、按日期分组 |
| topn | 2 | TopN 排序：GROUP BY + ORDER BY + LIMIT |
| redemption_rate | 2 | 业务指标计算：核销率（除法 + NULL 处理） |
| subquery | 2 | 子查询 / CTE：高于整体均值的券种 |
| dimension | 2 | 运营维度下钻：城市、司机等级 |

### 评测方法

采用 **执行准确率（Execution Accuracy）**，而非字符串比对 SQL——同一个问题可以有多种等价写法，只比对执行结果才公平。

评测脚本会先用固定随机种子生成一份**独立、可复现的评测库** `data/eval_nl2sql.db`（不污染业务库），再逐条执行、判分。

```bash
# 1) 只校验 gold SQL 本身（不需要 LLM Key，CI 可跑）
python eval/nl2sql/run_eval.py --seed 42 --drivers 60 --orders 800 --coupons 400

# 2) 跑真实 NL2SQL 管线准确率（需在 .env 配置 LLM_API_KEY）
python eval/nl2sql/run_eval.py --with-llm

# 3) 作为 pytest 的一部分运行
pytest tests/test_nl2sql_eval.py -q
```

### 当前结果

| 指标 | 结果 |
|------|------|
| Gold SQL 可执行率 | **22/22 = 100%** |
| Gold SQL 结果形态校验 | **22/22 = 100%** |
| 模型 NL2SQL 执行准确率 | 需配置 `LLM_API_KEY` 后运行 `--with-llm` 得出 |

评测集立刻就抓出了一个真实缺陷：**Q19（核销率高于整体的券种）** 的 CTE 里漏乘 `*100`，导致内外层百分比单位不一致、`HAVING` 条件恒成立，把低于整体的券种也误返回了。修正后 Q19 只返回「满减券 7.41%」（整体 5.5%），符合预期。这正是评测集存在的意义——**没有评测集，这类语义错误只会在生产里被业务方发现。**

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

本项目从原型到多Agent协作，经历了五个版本迭代：

```
v0.1.0 ──────▶ v0.2.0 ──────▶ v0.3.0 ──────▶ v0.4.0 ──────▶ v0.5.0
(原型)         (准生产)        (生产级)        (业务)          (多Agent)
   │               │               │               │               │
   ▼               ▼               ▼               ▼               ▼
┌─────────┐   ┌─────────┐   ┌─────────┐   ┌─────────┐   ┌─────────┐
│ 基础功能 │   │ P0+P1   │   │   P2    │   │ 业务功能 │   │多Agent  │
├─────────┤   ├─────────┤   ├─────────┤   ├─────────┤   ├─────────┤
│·NL2SQL  │   │·测试44个│   │·监控告警│   │·数据模拟│   │·4个Agent│
│·数据分析│   │·安全加固│   │·查询历史│   │·运营报告│   │·共享记忆│
│·Agent   │   │·用户认证│   │·数据导出│   │·异常检测│   │·消息传递│
│ 编排    │   │·Docker  │   │·可视化  │   │         │   │·自主决策│
│         │   │·前端界面│   │·性能优化│   │         │   │·Agent   │
│         │   │·API文档 │   │         │   │         │   │ 状态    │
└─────────┘   └─────────┘   └─────────┘   └─────────┘   └─────────┘
```

### 版本对比

> ✓ = 支持 / 已实现，✗ = 不支持 / 未实现

```text
┌────────────┬─────────┬─────────┬──────────────┬──────────────┬──────────────┐
│ 特性       │ v0.1.0  │ v0.2.0  │ v0.3.0       │ v0.4.0       │ v0.5.0       │
├────────────┼─────────┼─────────┼──────────────┼──────────────┼──────────────┤
│ 核心查询   │ ✓       │ ✓       │ ✓            │ ✓            │ ✓            │
│ Agent架构  │ 单Agent │ 单Agent │ 单Agent      │ 单Agent      │ 多Agent      │
│ 测试       │ ✗       │ ✓ 44个  │ ✓ 44个       │ ✓ 44个       │ ✓ 44个       │
│ 安全中间件 │ ✗       │ ✓ 4个   │ ✓ 4个        │ ✓ 4个        │ ✓ 4个        │
│ 用户认证   │ ✗       │ ✓ JWT   │ ✓ JWT        │ ✓ JWT        │ ✓ JWT        │
│ Docker     │ ✗       │ ✓ 3服务 │ ✓ 5服务      │ ✓ 5服务      │ ✓ 5服务      │
│ 监控       │ ✗       │ ✗       │ ✓ Prometheus │ ✓ Prometheus │ ✓ Prometheus │
│ 查询历史   │ ✗       │ ✗       │ ✓            │ ✓            │ ✓            │
│ 数据导出   │ ✗       │ ✗       │ ✓ CSV/JSON   │ ✓ CSV/JSON   │ ✓ CSV/JSON   │
│ 数据模拟   │ ✗       │ ✗       │ ✗            │ ✓            │ ✓            │
│ 运营报告   │ ✗       │ ✗       │ ✗            │ ✓ 周报/月报  │ ✓ 周报/月报  │
│ 异常检测   │ ✗       │ ✗       │ ✗            │ ✓ 6种        │ ✓ 6种        │
│ Agent数量  │ 1个     │ 1个     │ 1个          │ 1个          │ 4个          │
│ 自主决策   │ ✗       │ ✗       │ ✗            │ ✗            │ ✓            │
│ 共享记忆   │ ✗       │ ✗       │ ✗            │ ✗            │ ✓            │
│ API端点    │ 2个     │ 8个     │ 20+个        │ 30+个        │ 35+个        │
└────────────┴─────────┴─────────┴──────────────┴──────────────┴──────────────┘
```

### 改进优先级说明

项目采用 P0/P1/P2 + 业务功能 四级优先级进行改进：

- **P0（必须）**：测试、安全、错误处理 — 直接影响生产可用性
- **P1（重要）**：认证、文档、部署、前端 — 影响用户体验和运维
- **P2（优化）**：监控、历史、可视化、性能 — 提升系统质量和效率
- **业务功能**：数据模拟、运营报告、异常检测 — 贴近实际运营场景

## 更新日志

### v0.6.0 (2026-08-04) — NL2SQL 评测体系

补上项目此前最大的短板：**Text-to-SQL 没有量化指标**。

#### 📏 评测集
- 新增 `eval/nl2sql/evaluation_set.json` — 22 条中文业务问题 + gold SQL + 结果形态断言
  - 覆盖 8 类题型：单表聚合(4)、条件过滤(4)、多表JOIN(4)、时间过滤(2)、TopN(2)、核销率计算(2)、子查询/CTE(2)、运营维度下钻(2)
  - gold SQL 严格对齐 `data/schema_sqlite.sql` 真实列名（`order_time`/`order_amount`/`face_value`/`issued_at`）

#### 🔬 评测脚本
- 新增 `eval/nl2sql/run_eval.py`：
  - 固定种子生成**独立可复现评测库** `data/eval_nl2sql.db`，不污染业务库
  - 采用**执行准确率（Execution Accuracy）**，避免 SQL 字符串比对的等价写法误判
  - 无 LLM Key 时校验 gold SQL 正确性（CI 可跑）；`--with-llm` 时评测真实 NL2SQL 管线准确率
  - 用 DROP+CREATE 重建表而非删库文件，兼容只读/受限文件系统

#### ✅ 纳入测试套件
- 新增 `tests/test_nl2sql_eval.py`（22 条），测试总数 **44 → 66**
- 这是唯一走**真实 SQLite 库**端到端执行的测试，专门兜住 schema 契约漂移（对应「踩坑记录」坑 1、坑 2）

#### 🐛 评测集抓出的真实缺陷
- Q19（核销率高于整体的券种）CTE 内漏乘 `*100`，内外层百分比单位不一致导致 `HAVING` 恒成立，误返回低于整体的券种。修正后仅返回「满减券 7.41%」（整体 5.5%）

#### 🔧 附带增强
- `scripts/generate_data.py` 补充写入 `city` / `driver_level` 字段，使评测集能覆盖城市、司机等级等真实运营维度

### v0.5.0 (2026-08-05) — 多Agent协作架构

从单Agent+多工具架构升级为真正的多Agent协作架构，实现Agent间自主决策和协作。

#### 🤖 多Agent协作框架
- 新增 `app/agent/base.py` — Agent基类和协作基础设施：
  - `BaseAgent` 抽象基类（自主决策、工具调用、消息处理）
  - `OrchestratorAgent` 协调者（任务分配、结果整合）
  - `SharedMemory` 共享记忆（上下文同步、状态共享）
  - `Message` 消息类（Agent间通信、事件驱动）
  - `MessageType` 枚举（TASK/RESULT/QUERY/FEEDBACK/ERROR/STATUS）

#### 🧠 专业Agent实现
- 新增 `app/agent/agents.py` — 3个专业Agent：
  - **SQLAgent**：自主决策SQL生成和优化
    - 分析查询策略（直接/对比/排名/聚合）
    - 自主决定是否优化SQL
    - 自主决定结果采样
  - **AnalysisAgent**：自主决策分析角度和方法
    - 选择分析方法（趋势/分布/异常/排名/汇总）
    - 自主决定是否深入分析
    - 评估数据质量
  - **ReportAgent**：自主决策报告结构和重点
    - 确定报告焦点（优惠券/司机/订单/洞察）
    - 生成运营建议
    - 建议优先级排序
    - 计算置信度

#### 🔄 协调器升级
- 重写 `app/agent/orchestrator.py` — 多Agent协调器：
  - `MultiAgentOrchestrator` 类
  - 注册和管理多个Agent
  - 消息队列和日志
  - Agent执行轨迹追踪
  - 兼容旧接口

#### 🔌 API扩展
- 更新 `app/api/query.py` — 新增多Agent API：
  - `POST /api/query/multi-agent` — 多Agent协作查询
  - `GET /api/query/agent-status` — Agent系统状态

### v0.4.0 (2026-08-05) — 业务功能增强

基于网约车数据运营实际场景，新增数据模拟、运营报告、异常检测三大业务功能。

#### 📊 真实数据模拟
- 新增 `scripts/generate_data.py` — 网约车运营数据生成器：
  - 支持自定义：天数（`--days`）、司机数（`--drivers`）、订单数（`--orders`）、卡券数（`--coupons`）
  - 生成数据：司机信息、卡券类型、卡券发放记录、订单记录、核销记录
  - 真实模拟：城市分布、时段高峰、金额分布、核销率、司机等级
  - 使用示例：`python scripts/generate_data.py --days 30 --drivers 100 --orders 5000`

#### 📈 运营报告自动生成
- 新增 `app/report/generator.py` — 运营报告生成器：
  - 核心指标：订单数/金额/完成率/卡券使用率
  - 趋势分析：近7天订单/金额/司机趋势
  - 卡券分析：各类型核销率对比
  - TOP司机：按金额排名
  - 时段分布：24小时订单分布
  - 运营建议：基于数据的策略建议
- 新增 `app/api/report.py` — 6 个 API：
  - `GET /api/report/generate` — 生成运营报告（支持 week/month）
  - `GET /api/report/metrics` — 获取核心指标
  - `GET /api/report/trend` — 获取趋势数据
  - `GET /api/report/coupon-analysis` — 卡券分析
  - `GET /api/report/top-drivers` — TOP司机排名
  - `GET /api/report/hourly-distribution` — 时段分布

#### 🚨 异常检测与告警
- 新增 `app/anomaly/detector.py` — 异常检测器：
  - 检测类型：订单下降/金额下降/核销率下降/司机下降/异常激增/低核销率
  - 异常级别：INFO / WARNING / CRITICAL
  - 阈值配置：可自定义各指标告警阈值
- 新增 `app/api/anomaly.py` — 3 个 API：
  - `GET /api/anomaly/detect` — 检测所有异常
  - `GET /api/anomaly/summary` — 异常摘要
  - `GET /api/anomaly/health` — 系统健康检查

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

## 踩坑记录与复盘（真实记录）

> 本节如实记录项目从原型到生产级演进过程中真实踩过的坑、修复过程与教训。这些坑大多在"单测全绿"的情况下仍未被发现，直到端到端实测才暴露——对面试复盘和后续维护都有价值。

### 坑 1：Schema 列名漂移（最严重，导致核心功能全失效）

**现象**：服务能启动、44 个单元测试全过，但真实数据模拟、异常检测、报告生成、仪表盘 4 个功能模块全部跑不起来。

**根因**：`data/schema_sqlite.sql` 在建库时把关键列名做了规范化（如 `orders.order_date` → `order_time`、`amount` → `order_amount`），但 4 处业务代码仍引用旧的列名，且彼此互不同步，形成"schema 已改、代码没跟"的漂移。

**具体故障点**（均指向 SQLite `no such column` 报错）：

| 文件 | 旧列名（错误） | schema 真实列名 | 后果 |
|------|---------------|----------------|------|
| `scripts/generate_data.py` | `order_date`/`amount`/`issue_date`/`valid_until`/`value`/`validity_days` | `order_time`/`order_amount`/`issued_at`/`expired_at`/`face_value`/`valid_days` | 数据生成直接失败，无任何演示数据 |
| `app/anomaly/detector.py` | `order_date`/`amount`/`issue_date`/`ct.value` | `order_time`/`order_amount`/`issued_at`/`ct.face_value` | 异常检测接口报 no such column，整体失效 |
| `app/report/generator.py` | `order_date`/`issue_date`/`o.amount` | `order_time`/`issued_at`/`o.order_amount` | 报告 SQL 报错 |
| `app/api/dashboard.py` | （无）直接 return 写死的 0 值 | 改为真实查询 | 仪表盘永远是空壳，前端展示全为 0 |

**修复**：统一对齐到 `data/schema_sqlite.sql` 的真实列；`dashboard.py` 由空壳改为真实查库（卡券总数 / 核销率 / 各券种表现 / Top5 司机）。提交 `dc45a49`。

**教训**：
- 改 schema 必须全局检索所有引用点（代码 + 脚本 + 测试），不能只改建库语句。
- 单测全 mock 数据库会掩盖 schema 契约问题，**必须有一次端到端真实 DB 集成测试**才能证明系统真的能跑。
- 建议：把列名集中为常量或用 ORM 映射，避免表名/列名字符串散落各处。

### 坑 2：44 个测试全绿 ≠ 系统可用（mock 测试的盲区）

**现象**：`pytest` 报告 44 passed，但 `uvicorn` 一启动、跑真实功能就崩。

**根因**：所有 API / 业务测试都用 mock 把数据库层替换掉了，没有一条用例真正连过 SQLite 执行过建表 / 插入 / 查询。schema 漂移和空壳接口在 mock 下完全不可见。

**修复**：补一次冒烟测试——`generate_data.py` 真实灌库后，逐个请求 `/api/dashboard/`、`/api/anomaly/health`、`/api/monitoring/metrics`，确认返回真实数据。

**教训**：mock 测试只能验证"逻辑对不对"，验证不了"集成通不通"。生产级项目必须保留少量真实 DB 的集成测试（如 pytest 临时建内存 SQLite）。

### 坑 3：.env 不进版本库，跨机器配置丢失

**现象**：在 A 机器配好的 `LLM_API_KEY`，到 B 机器 `git pull` 后 NL2SQL / 报告等 LLM 功能全部不可用。

**根因**：`.env` 被 `.gitignore` 忽略（正确做法，避免泄露密钥），所以不会随仓库同步。

**使用提醒**：
- 每台机器首次拉取后必须 `cp .env.example .env` 并填 `LLM_API_KEY`。
- 无 key 时服务仍能启动、非 LLM 功能（仪表盘 / 异常 / 监控）可用；`/api/query/` 会因缺 key 优雅返回 500，这是预期行为。

**教训**：密钥类配置靠 `.env.example` + 文档约定，不要指望自动同步；部署 / 演示前务必先检查 `.env` 是否存在。

### 坑 4："多 Agent 协作"命名与实现一度不符（已纠正）

**现象**：v0.1~v0.4 版本 README 与代码都称"多 Agent 协作"，但实际是固定顺序的流水线（Planner → SQLTool → AnalysisTool → ReportTool），Agent 之间并无自主决策或消息传递。

**根因**：早期为了贴合"Agent 工作流"定位，把"单 Agent + 多工具"表述写成了"多 Agent 协作"，存在过度包装。

**修复**：v0.5.0 真正落地了 Orchestrator + 3 个专业化 Agent（SQLAgent / AnalysisAgent / ReportAgent）+ 共享记忆（SharedMemory）的协作框架，并在文档中诚实区分演进前后。面试讲解时建议如实说明：早期为单 Agent 编排，v0.5.0 才升级为真正的多 Agent 协作。

**教训**：技术叙事要与实际架构一致，面试官很容易追问"这几个 Agent 是怎么通信的"。

### 坑 5：README 表格在终端 / 部分渲染器中错位

**现象**：版本对比表用 Markdown 表格 + ✅/❌ emoji，在 CJK 字符 + emoji 混排下因宽度不一经常对不齐。

**修复**：改用等宽代码块（`text`）+ 固定宽度符号 `✓` / `✗`，保证任何渲染器下对齐。见上方「版本对比」一节。

**教训**：面向"会被原样拷贝 / 终端查看"的文档，优先用等宽 Unicode 表，慎用 emoji。

### 坑 6：旧进程占用端口导致测到旧代码（运维提醒）

**现象**：实测时端口 8001 被一个更早启动的旧 `uvicorn` 实例接管，curl 打到的其实是旧代码，一度让人误以为修复没生效。

**修复**：用 `netstat -ano | findstr :8001` 找到残留 PID，`taskkill /PID <pid> /F` 强杀后，再用最新代码重启实例复验。

**教训**：验证修复前先确认端口没有被旧进程占用；本地开发建议用 `--reload` 或固定前后台任务管理，避免多个实例并存。

## 贡献指南

1. Fork 项目
2. 创建功能分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 创建 Pull Request

## 许可证

MIT License - 详见 [LICENSE](LICENSE) 文件
