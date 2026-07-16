from __future__ import annotations
from pathlib import Path
from app.db.connection import execute_sql


def describe_tables() -> str:
    schema_path = Path(__file__).resolve().parent.parent.parent / "data" / "schema.sql"
    if schema_path.exists():
        return schema_path.read_text(encoding="utf-8")
    return ""


def get_table_info() -> str:
    try:
        tables = ["drivers", "coupon_types", "coupons", "orders", "redemptions"]
        info_parts = []
        for table in tables:
            rows, cols = execute_sql(f"DESCRIBE {table}")
            info_parts.append(f"表名: {table}")
            for row in rows:
                info_parts.append(f"  {row['Field']} ({row['Type']})")
        return "\n".join(info_parts)
    except Exception as e:
        return f"无法获取表信息: {e}"
