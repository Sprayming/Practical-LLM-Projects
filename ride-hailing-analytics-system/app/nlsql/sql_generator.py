from __future__ import annotations
from openai import OpenAI
from app.config import settings
from app.nlsql.schema_parser import describe_tables


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
6. 本数据库为 **SQLite**，必须使用 SQLite 语法，严禁 MySQL 语法：
   - 日期用 date('now')、date('now','-7 days')、strftime('%Y-%m-%d', col) 等函数
   - 禁止 CURDATE()、DATE_SUB()、DATE_ADD()、WEEKDAY()、DATEDIFF()、NOW()
   - 上周范围示例：order_time >= date('now','weekday 1','-7 days') AND order_time < date('now','weekday 1')
7. 订单状态字段 `status` 的值用英文：completed(已完成) / cancelled(已取消) / refunded(已退款)，生成条件时务必用英文字面值
8. 列别名禁止包含 `%` 与括号（用 '核销率' 而非 '核销率(%)'），且别名必须加单引号，否则 SQLite 报语法错误
""".strip()


def generate_sql(question: str) -> tuple[str, str]:
    client = OpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)
    table_schema = describe_tables()
    
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
    lines = content.strip().split("\n")
    
    sql_lines = []
    explanation_lines = []
    in_sql = False
    for line in lines:
        if line.strip().upper().startswith("SELECT"):
            in_sql = True
        if in_sql and not line.strip().startswith("`"):
            sql_lines.append(line)
        elif not in_sql and not line.strip().startswith("`"):
            explanation_lines.append(line)
    
    sql = " ".join(sql_lines).strip()
    # 去掉模型附在 SQL 后的解释文字（分号 / ** 标记 / 中文"解释"字样之后全部丢弃）
    for marker in (";", "**", "解释", "说明", "注："):
        if marker in sql:
            sql = sql.split(marker)[0].strip()
    sql = sql.strip("`").strip()
    explanation = "\n".join(explanation_lines).strip()

    return sql, explanation
