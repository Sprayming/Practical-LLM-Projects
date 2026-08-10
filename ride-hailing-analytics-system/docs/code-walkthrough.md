# ride-hailing-analytics-system · 代码级逐函数详解（能凭自己写出来版）

> 配套视频：`docs/architecture-explainer.html`（每步讲解同步显示真实源码）。
> 本文是**逐函数完整版**：每个函数都贴真实源码 + 行内讲解，配合视频一起看，建立「数据流 ↔ 具体函数」的对应关系。
> 读本文前建议先读 `student.md`（MVC 三层对照 + 自测卡）。

---

## 0. 骨架：`app/main.py` —— 一切从路由装配开始

```python
# 注册错误处理器
register_error_handlers(app)

# 添加监控中间件（最外层）
app.add_middleware(MonitoringMiddleware)
app.add_middleware(SlowRequestMiddleware, slow_threshold=2.0)

# 添加安全中间件（重点！）
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestSizeLimitMiddleware, max_size=1024 * 1024)  # 1MB
app.add_middleware(RateLimitMiddleware, requests_per_minute=60)
app.add_middleware(SQLInjectionMiddleware)

# 注册路由
app.include_router(query.router)        # /api/query   ← 问答入口（单Agent + 多Agent）
app.include_router(dashboard.router)    # /api/dashboard
app.include_router(monitoring_router)   # /metrics /health
# history / tasks / auth / report / anomaly 用 try/except 可选挂载

# 生命周期：启动时建库
@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.db.connection import init_db
    init_db()   # 读 schema_sqlite.sql 建表
    yield
```

**记住**：`main.py` 只做「装配」。两条入口都在 `app/api/query.py`：
- `POST /api/query/` —— 单 Agent 模式（线性流水线，本项目核心）
- `POST /api/query/multi-agent` —— 多 Agent 协作模式（SQLAgent → AnalysisAgent → ReportAgent）

---

## 1. 单 Agent 链路：自然语言 → SQL → 数据 → 洞察

### 1.1 入口 `app/api/query.py:20` `natural_language_query()`

```python
@router.post("/", response_model=AnalysisResult)
async def natural_language_query(request: QueryRequest):
    start = time.perf_counter()
    try:
        # ① 输入净化 + 校验
        question = sanitize_input(request.question)
        is_valid, error_msg = validate_question(question)
        if not is_valid:
            raise ValidationError(error_msg, "INVALID_QUESTION")

        # ② 生成 SQL（LLM）
        try:
            sql, explanation = generate_sql(question)
        except Exception as e:
            raise LLMError("SQL生成失败，请稍后重试", "SQL_GENERATION_FAILED")
        if not sql:
            raise ValidationError("无法生成有效的SQL查询", "NO_SQL_GENERATED")

        # ③ 执行 SQL
        try:
            rows, columns = run_sql(sql)
        except Exception as e:
            raise DatabaseError("数据库查询失败，请稍后重试", "SQL_EXECUTION_FAILED")

        # ④ 数据分析（LLM）
        try:
            summary = interpret(question, sql, rows)
        except Exception as e:
            summary = f"数据查询完成，共返回 {len(rows)} 条记录"

        # ⑤ 生成建议（LLM）
        try:
            advice = recommend(question, rows)
        except Exception as e:
            advice = "暂无具体建议"

        elapsed = (time.perf_counter() - start) * 1000
        return AnalysisResult(
            question=question, sql=sql, summary=summary,
            insight=explanation, recommendation=advice,
            data=rows[:100], latency_ms=round(elapsed, 2),
        )
    except (ValidationError, DatabaseError, LLMError):
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="查询失败，请稍后重试")
```

**要点**：这是一条**五段式线性流水线**，每段都 try/except 包裹，且 API 失败有优雅降级（如 `interpret` 失败就返回「共返回 N 条记录」）。这是本项目与 legal-doc-rag 最大的不同——**没有向量库、没有 RAG 重排**，而是走「LLM 生成 SQL → 真数据库执行 → LLM 解读」的 NL2SQL 路线。

### 1.2 输入安全 `app/security/validators.py`

```python
def sanitize_input(text: str, max_length: int = 2048) -> str:
    if not text:
        return ""
    text = text.strip()
    if len(text) > max_length:          # ① 限长，防超长输入
        text = text[:max_length]
    return text

def validate_question(question: str) -> tuple[bool, str]:
    if not question:
        return False, "问题不能为空"
    question = question.strip()
    if len(question) < 2:
        return False, "问题太短"
    if len(question) > 2048:
        return False, "问题太长"
    # ② 防 XSS / 注入型输入
    malicious_patterns = [
        r"<script.*?>.*?</script>",
        r"javascript:",
        r"on\w+\s*=",
        r"expression\s*\(",
    ]
    for pattern in malicious_patterns:
        if re.search(pattern, question, re.IGNORECASE):
            return False, "问题包含不允许的内容"
    return True, ""
```

**要点**：`sanitize_input` 只做去空格 + 限长；真正的恶意输入（`<script>`、事件处理器）由 `validate_question` 的 `malicious_patterns` 拦。注意这里**只校验、不直接拼 SQL**——SQL 安全另有第二道防线（见 1.5）。

### 1.3 Schema 注入 `app/nlsql/schema_parser.py`

```python
def describe_tables() -> str:
    schema_path = Path(__file__).resolve().parent.parent.parent / "data" / "schema.sql"
    if schema_path.exists():
        return schema_path.read_text(encoding="utf-8")   # 读 data/schema.sql 全文
    return ""
```

**要点**：把 `data/schema.sql` 的 DDL 原文喂给 LLM，让模型「知道有哪些表、哪些字段」才能写出正确 SQL。这是 NL2SQL 的关键上下文。

### 1.4 NL→SQL `app/nlsql/sql_generator.py:22` `generate_sql()`

```python
SYSTEM_PROMPT = """
你是一个专业的 SQL 分析师。根据数据库 Schema 和用户问题，生成对应的 SQL 查询语句。
数据库表结构：
{table_schema}
规则：
1. 只生成 SELECT 查询，不生成 INSERT/UPDATE/DELETE
2. 使用中文别名时加引号
3. 涉及金额时保留两位小数
4. 涉及时间范围时优先使用最近30天
5. 返回格式：SQL + 一句话解释这个 SQL 在查什么
""".strip()

def generate_sql(question: str) -> tuple[str, str]:
    client = OpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)
    table_schema = describe_tables()                      # ① 注入 schema
    prompt = SYSTEM_PROMPT.format(table_schema=table_schema)
    response = client.chat.completions.create(
        model=settings.llm_model,
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"用户问题：{question}\n请生成 SQL 并解释。"},
        ],
        temperature=settings.llm_temperature,
    )
    content = response.choices[0].message.content
    # ② 解析：从 LLM 返回里拆出 SQL 与解释
    sql_lines, explanation_lines = [], []
    in_sql = False
    for line in content.strip().split("\n"):
        if line.strip().upper().startswith("SELECT"):
            in_sql = True
        if in_sql and not line.strip().startswith("`"):
            sql_lines.append(line)
        elif not in_sql and not line.strip().startswith("`"):
            explanation_lines.append(line)
    sql = " ".join(sql_lines).strip()
    explanation = "\n".join(explanation_lines).strip()
    return sql, explanation
```

**要点**：`generate_sql` 做的是「prompt 工程 + 文本解析」。难点在第 ② 步：LLM 返回是自由文本（SQL 混着解释），必须用「以 `SELECT` 开头进入 SQL 区、反引号行跳过」这个**启发式规则**把 SQL 抠出来。这就是为什么系统提示里强调「返回格式：SQL + 解释」——靠格式约定换可解析性。

### 1.5 SQL 执行与安全 `app/nlsql/sql_executor.py`

```python
def validate_sql(sql: str) -> bool:
    sql_upper = sql.strip().upper()
    if not sql_upper.startswith("SELECT"):          # ① 必须是 SELECT
        return False
    forbidden = ["INTO", "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "TRUNCATE", "CREATE"]
    for kw in forbidden:
        pattern = r"\b" + kw + r"\b"                 # ② 禁止写操作/ DDL 关键词
        if re.search(pattern, sql_upper):
            return False
    return True

def run_sql(sql: str) -> tuple[list[dict], list[str]]:
    if not validate_sql(sql):                        # ③ 执行前再卡一道
        return [], []
    try:
        rows, columns = execute_sql(sql)             # → app.db.connection.execute_sql
        return rows, columns
    except Exception as e:
        logger.error("SQL execution failed: {}", e)
        return [], []
```

**要点**：这是**第二道 SQL 安全闸**（第一道是 `validators` 的输入校验）。`validate_sql` 用「白名单前缀 SELECT + 黑名单关键词」双保险，即使 LLM 被诱导生成 `DROP TABLE`，也会被拦在 `execute_sql` 之前。**两道防线缺一不可**：前端 `SQLInjectionMiddleware` 防注入型输入，这里防「合法输入但危险 SQL」。

`execute_sql`（`app/db/connection.py`）：

```python
def execute_sql(sql: str) -> tuple[list[dict], list[str]]:
    conn = get_connection()                          # sqlite3.connect(data/ride_hailing.db)
    try:
        cursor = conn.execute(sql)
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        rows = [dict(row) for row in cursor.fetchall()]   # Row → dict
        return rows, columns
    except Exception as e:
        logger.error("SQL execute error: {}", e)
        return [], []
    finally:
        conn.close()
```

**要点**：用 `sqlite3.Row` + `row_factory` 把每行转成 `dict`，前端直接拿到字段名。异常被吞掉返回空——不向上抛，避免泄露数据库细节。

### 1.6 数据分析 `app/analysis/interpreter.py:21` `interpret()`

```python
INTERPRETER_PROMPT = """
你是一个数据分析师。根据用户的原始问题和 SQL 查询结果，给出数据解读。
数据：{data}
原始问题：{question}
请从以下角度分析：
1. 数据概况：关键指标和趋势
2. 业务洞察：这些数据说明了什么问题
3. 异常发现：是否有需要关注的反常数据
""".strip()

def interpret(question: str, sql: str, rows: list[dict]) -> str:
    if not rows:
        return "查询未返回数据，请检查问题是否准确。"     # 空结果直接回退
    client = OpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)
    prompt = INTERPRETER_PROMPT.format(question=question, data=str(rows[:50]))  # 只取前50行
    response = client.chat.completions.create(
        model=settings.llm_model,
        messages=[{"role": "user", "content": prompt}],
        temperature=settings.llm_temperature,
    )
    return response.choices[0].message.content
```

**要点**：`interpret` 把「问题 + 查回的数据」再喂一次 LLM，产出业务解读。`rows[:50]` 截断防 token 爆炸。空结果不调 LLM，直接返回提示。

### 1.7 运营建议 `app/analysis/recommender.py:19` `recommend()`

```python
RECOMMENDER_PROMPT = """
你是一个运营策略顾问。根据用户的业务问题和数据分析结果，给出可执行的运营建议。
业务问题：{question}
数据分析结果：{data}
请给出：
1. 核心结论
2. 具体行动建议（2-3条）
3. 预期效果
""".strip()

def recommend(question: str, data: list[dict]) -> str:
    if not data:
        return "暂无数据支撑建议。"
    client = OpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)
    prompt = RECOMMENDER_PROMPT.format(question=question, data=str(data[:50]))
    response = client.chat.completions.create(
        model=settings.llm_model,
        messages=[{"role": "user", "content": prompt}],
        temperature=settings.llm_temperature,
    )
    return response.choices[0].message.content
```

**要点**：与 `interpret` 同构，只是 Prompt 角色换成「运营策略顾问」。三段式 LLM 调用（generate_sql / interpret / recommend）是本项目「LLM 编排」的核心范式。

---

## 2. 多 Agent 链路：Orchestrator 编排三个专家 Agent

### 2.1 调度器入口 `app/agent/orchestrator.py:71` `MultiAgentOrchestrator.process()`

```python
async def process(self, question: str) -> Dict[str, Any]:
    user_message = Message(sender="user", receiver="Orchestrator",
                            msg_type=MessageType.TASK, content={"question": question})
    result = await self.orchestrator.process(user_message)   # 交给协调者
    final_result = {
        "question": question,
        "result": result.content if result else {},
        "agent_trace": self._get_agent_trace(),               # 消息轨迹（可观测）
        "shared_context": self.shared_memory.get_all(),       # 共享记忆快照
        "agents_used": [self.sql_agent.name, self.analysis_agent.name, self.report_agent.name],
    }
    return final_result
```

`__init__` 里把三个 Agent 注册给协调者，并建立共享记忆 `SharedMemory` 与消息队列：

```python
self.shared_memory = SharedMemory()
self.orchestrator = OrchestratorAgent(shared_memory=self.shared_memory, message_queue=self._handle_message)
self.sql_agent = SQLAgent(shared_memory=self.shared_memory)
self.analysis_agent = AnalysisAgent(shared_memory=self.shared_memory)
self.report_agent = ReportAgent(shared_memory=self.shared_memory)
self.orchestrator.register_agent(self.sql_agent)
self.orchestrator.register_agent(self.analysis_agent)
self.orchestrator.register_agent(self.report_agent)
```

### 2.2 协调者 `app/agent/base.py:181` `OrchestratorAgent.process()`

```python
async def process(self, message: Message) -> Optional[Message]:
    plan = await self._create_plan(message)              # ① 制定计划
    self.shared_memory.set("current_plan", plan)
    results = {}
    for step in plan["steps"]:                           # ② 按依赖顺序执行
        agent_name = step["agent"]
        if agent_name not in self.agents:
            continue
        agent = self.agents[agent_name]
        task_msg = self.send_message(receiver=agent_name, msg_type=MessageType.TASK,
                                     content={"task": step["task"],
                                              "context": self.shared_memory.get_all(),
                                              "depends_on": step.get("depends_on", [])})
        result = await agent.process(task_msg)            # ③ 等 Agent 返回
        if result:
            results[agent_name] = result.content
            self.shared_memory.set(f"result_{agent_name}", result.content)
    final_result = self._integrate_results(results)      # ④ 整合
    self.shared_memory.set("final_result", final_result)
    return Message(sender=self.name, receiver="user", msg_type=MessageType.RESULT, content=final_result)
```

`_create_plan` 固定生成三步：`SQLAgent` → `AnalysisAgent`（依赖 SQLAgent）→ `ReportAgent`（依赖 AnalysisAgent）。**这就是「数据流」**：SQL 结果写入 `shared_memory["sql_result"]`，分析 Agent 读它，报告 Agent 再读分析结果。

### 2.3 共享记忆与消息 `app/agent/base.py`

```python
class SharedMemory:
    def __init__(self):
        self.context: Dict[str, Any] = {}      # 所有 Agent 共享的键值空间
        self.history: List[Dict] = []          # 操作历史（限长100）
    def set(self, key, value):
        self.context[key] = value
        self._record("set", key, value)
    def get(self, key, default=None):
        return self.context.get(key, default)
    def get_all(self) -> Dict:
        return self.context.copy()
```

```python
class Message:
    def __init__(self, sender, receiver, msg_type, content, conversation_id=None):
        self.id = str(uuid.uuid4())[:8]
        self.sender = sender
        self.receiver = receiver
        self.msg_type = msg_type
        self.content = content
        self.conversation_id = conversation_id or str(uuid.uuid4())[:8]
        self.requires_response = msg_type in [MessageType.TASK, MessageType.QUERY]
```

**要点**：多 Agent 协作的「胶水」就是 `SharedMemory`（黑板式共享状态）+ `Message`（Agent 间通信）。`requires_response` 标记这条消息是否需要对方回。

### 2.4 三个专家 Agent `app/agent/agents.py`

**SQLAgent.process**（核心：复用单 Agent 的 NL2SQL 能力）：

```python
async def process(self, message: Message) -> Optional[Message]:
    task = message.content.get("task", "")
    context = message.content.get("context", {})
    question = context.get("current_plan", {}).get("question", task)
    try:
        strategy = self._analyze_query_strategy(question)   # 自主决策查询策略
        sql, explanation = generate_sql(question)           # 复用 NL2SQL
        if not sql:
            return self._create_error_response(message, "无法生成SQL")
        if self._should_optimize(sql):                      # 自主决定是否优化
            sql = self._optimize_sql(sql)
        rows, columns = run_sql(sql)                        # 复用执行器
        if len(rows) > 100:
            rows = rows[:100]                               # 自主采样
        result = {"sql": sql, "explanation": explanation, "data": rows, "columns": columns, ...}
        self.shared_memory.set("sql_result", result)        # 写入共享记忆
        return Message(sender=self.name, receiver=message.sender,
                       msg_type=MessageType.RESULT, content=result)
    except Exception as e:
        return self._create_error_response(message, str(e))
```

**要点**：`SQLAgent` 本质是把单 Agent 链路的「generate_sql + run_sql」封装成 Agent，并加了「自主决策」：
- `_analyze_query_strategy`：按关键词判断是对比/排名/聚合类问题（决定 approach）
- `_should_optimize`：SQL 超 200 字或含子查询就自动加 `LIMIT 1000`
- 结果写入 `shared_memory["sql_result"]`，下游 Agent 才能拿到

**AnalysisAgent.process**：从 `shared_memory.get("sql_result")` 拿数据 → `_select_analysis_method`（按关键词选趋势/分布/异常/排名分析）→ `_perform_analysis`（基础统计 mean/min/max/count）→ `_generate_insights`（生成洞察）→ 写入 `shared_memory["analysis_result"]`。

**ReportAgent.process**：读 `sql_result` + `analysis_result` → `_determine_focus`（按关键词定重点：优惠券/司机/订单）→ `_generate_recommendations` → `_prioritize_recommendations`（按 high/medium/low 排序）→ `_format_output`（Markdown 报告）→ 写入 `shared_memory["report_result"]`。

**一句话总结多 Agent**：Orchestrator 把问题拆成「写 SQL → 分析 → 报告」三步，三个 Agent 通过 `SharedMemory` 黑板接力，每步都「自主决策 + 写共享状态」。比单 Agent 多了**可观测轨迹**（`agent_trace`）和**职责分离**，但底层 NL2SQL/执行逻辑完全复用。

---

## 3. 安全体系（本项目重点考察点）

### 3.1 中间件 `app/security/middleware.py`（main.py 中挂载）

`main.py` 挂了 4 道安全中间件（由外到内）：
- `MonitoringMiddleware` / `SlowRequestMiddleware` —— 监控（非安全，但排最外）
- `SecurityHeadersMiddleware` —— 加安全响应头
- `RequestSizeLimitMiddleware(max_size=1MB)` —— 防大请求 DoS
- `RateLimitMiddleware(requests_per_minute=60)` —— 限流
- `SQLInjectionMiddleware` —— 注入拦截

> 注：当前 `SQLInjectionMiddleware` 主要做输入层防护；**真正的 SQL 安全兜底在 `sql_executor.validate_sql`**（见 1.5）。两层配合才是完整防护。

### 3.2 鉴权 `app/auth/jwt_handler.py`

```python
SECRET_KEY = "your-secret-key-keep-it-secret-in-production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

def create_access_token(data: dict, expires_delta=None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=60))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def verify_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError as e:
        logger.warning("Token验证失败: {}", e)
        return None
```

**要点**：HS256 对称 JWT，默认 60 分钟过期。`verify_token` 失败返回 `None`（不抛），由 `auth/dependencies.py:get_current_user_optional` 决定是否放行。⚠️ 注意 `SECRET_KEY` 是硬编码常量，**生产环境必须从环境变量读**（这是面试常考点：密钥泄露 = 可伪造任意 token）。

---

## 4. 两条链路的函数调用对照

```
【单 Agent】POST /api/query/
  → sanitize_input()          [validators.py]        去空格+限长
  → validate_question()       [validators.py]        防 XSS/注入输入
  → generate_sql()            [sql_generator.py]     LLM 生成 SQL（注入 schema）
  → describe_tables()         [schema_parser.py]     读 data/schema.sql
  → run_sql()                 [sql_executor.py]      先 validate_sql() 双保险
  → validate_sql()            [sql_executor.py]      SELECT 白名单 + 关键词黑名单
  → execute_sql()             [db/connection.py]     sqlite 执行，Row→dict
  → interpret()               [analysis/interpreter.py]  LLM 数据解读
  → recommend()               [analysis/recommender.py] LLM 运营建议
  → AnalysisResult(...)       [query.py]             组装返回

【多 Agent】POST /api/query/multi-agent
  → multi_agent_orchestrator.process()   [orchestrator.py]
  → OrchestratorAgent.process()          [base.py]     制定计划+顺序执行+整合
  → SQLAgent.process()                   [agents.py]    generate_sql+run_sql → shared_memory
  → AnalysisAgent.process()              [agents.py]    读 sql_result → 分析 → shared_memory
  → ReportAgent.process()                [agents.py]    读分析结果 → 建议 → 报告
```

**两条链路的关系**：多 Agent 模式**不是另起炉灶**，而是把单 Agent 的 `generate_sql + run_sql + interpret` 拆给三个 Agent，靠 `SharedMemory` 接力。底层数据库执行 `execute_sql` 与 SQL 安全 `validate_sql` **完全共用**。

---

## 5. 自测函数（遮住代码能写出来吗？）

1. `natural_language_query` 的五段流水线，每段失败时怎么降级？
2. `validate_question` 拦哪四类恶意模式？它和 `validate_sql` 各管什么？
3. `generate_sql` 怎么从 LLM 自由文本里把 SQL 抠出来？（提示：`SELECT` 开头 + 反引号跳过）
4. `describe_tables` 读的是哪个文件？为什么必须注入 schema？
5. `validate_sql` 的双保险具体是什么？（SELECT 前缀 + 8 个黑名单关键词）
6. `execute_sql` 怎么把 sqlite 行变成 dict？异常时返回什么？
7. `interpret` / `recommend` 为什么要 `rows[:50]` 截断？
8. `OrchestratorAgent.process` 的执行顺序是靠什么驱动的？（`_create_plan` 的 `steps` + `depends_on`）
9. `SharedMemory` 在多 Agent 里扮演什么角色？`sql_result` 被谁写、谁读？
10. `SECRET_KEY` 硬编码有什么风险？JWT 过期时间默认多少？（60 分钟）

---

## 6. 与 legal-doc-rag 的对照（你已经熟的那个）

| 维度 | legal-doc-rag | ride-hailing-analytics-system |
|------|---------------|-------------------------------|
| 核心范式 | RAG（检索增强生成） | NL2SQL（自然语言转 SQL） |
| 数据底座 | Chroma 向量库（按租户物理隔离） | SQLite（单库，schema.sql 建表） |
| 检索 | 混合检索 + BGE 重排 | 直接 `execute_sql` 真查数据库 |
| 隔离 | `tenant_id` 贯穿全链路（物理目录） | 无多租户，靠 JWT 鉴权 + SQL 白名单 |
| LLM 调用 | 1 次（生成答案） | 3 次（生成 SQL / 解读 / 建议） |
| 多 Agent | 无 | 有（SQL/Analysis/Report 三 Agent + 共享记忆） |
| 安全重点 | 路径穿越防护（落盘） | SQL 注入防护（validate_sql + 中间件） |

**一句话**：legal-doc-rag 是「把文档向量化后检索再生成」，ride-hailing 是「让 LLM 写 SQL 直接查业务库再生成洞察」。两者都把「用户问题」当入口，都把 LLM 当编排核心，但数据访问方式截然不同。
