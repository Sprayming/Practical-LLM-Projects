import json, requests
from typing import Optional
from app.nlsql.sql_generator import generate_sql
from app.nlsql.sql_executor import run_sql


class SQLTool:
    def execute(self, step, question: str) -> dict:
        sql, explanation = generate_sql(step.description or question)
        if not sql:
            return {"type": "data", "error": "Failed to generate SQL", "sql": "", "rows": []}
        rows, columns = run_sql(sql)
        return {
            "type": "data",
            "sql": sql,
            "explanation": explanation,
            "rows": rows[:50],
            "row_count": len(rows),
            "columns": columns,
            "summary": f"SQL: {sql}\\nResult: {len(rows)} rows\\n" + json.dumps(rows[:5], ensure_ascii=False, default=str),
        }
