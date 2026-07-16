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
    explanation = "\n".join(explanation_lines).strip()
    
    return sql, explanation
