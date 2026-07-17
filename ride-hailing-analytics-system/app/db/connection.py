from __future__ import annotations
import sqlite3
from pathlib import Path
from loguru import logger

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "ride_hailing.db"
SQL_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "schema_sqlite.sql"

def get_connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    schema = SQL_PATH.read_text(encoding="utf-8")
    conn.executescript(schema)
    conn.commit()
    conn.close()
    logger.info("SQLite DB initialized: {}", DB_PATH)

def execute_sql(sql: str) -> tuple[list[dict], list[str]]:
    conn = get_connection()
    try:
        cursor = conn.execute(sql)
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        rows = [dict(row) for row in cursor.fetchall()]
        return rows, columns
    except Exception as e:
        logger.error("SQL execute error: {}", e)
        return [], []
    finally:
        conn.close()
