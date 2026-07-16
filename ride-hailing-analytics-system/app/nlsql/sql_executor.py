from __future__ import annotations
import re
from loguru import logger
from app.db.connection import execute_sql


def validate_sql(sql: str) -> bool:
    sql_upper = sql.strip().upper()
    if not sql_upper.startswith("SELECT"):
        logger.warning("非 SELECT 语句被拒绝: {}", sql[:100])
        return False
    
    forbidden = ["INTO", "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "TRUNCATE", "CREATE"]
    for kw in forbidden:
        pattern = r"\b" + kw + r"\b"
        if re.search(pattern, sql_upper):
            logger.warning("包含危险关键词: {}", kw)
            return False
    
    return True


def run_sql(sql: str) -> tuple[list[dict], list[str]]:
    if not validate_sql(sql):
        return [], []
    
    try:
        rows, columns = execute_sql(sql)
        logger.info("SQL executed: {} rows returned", len(rows))
        return rows, columns
    except Exception as e:
        logger.error("SQL execution failed: {}", e)
        return [], []
