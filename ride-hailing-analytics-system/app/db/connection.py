from __future__ import annotations
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from loguru import logger
from app.config import settings


def get_engine():
    url = f"mysql+pymysql://{settings.db_user}:{settings.db_password}@{settings.db_host}:{settings.db_port}/{settings.db_name}?charset=utf8mb4"
    return create_engine(url, echo=settings.debug)


engine = None
SessionLocal = None


def init_db():
    global engine, SessionLocal
    engine = get_engine()
    SessionLocal = sessionmaker(bind=engine)
    logger.info("Database connection established")


def get_session():
    if SessionLocal is None:
        init_db()
    return SessionLocal()


def execute_sql(sql: str) -> tuple[list[dict], list[str]]:
    with get_session() as session:
        result = session.execute(text(sql))
        columns = list(result.keys())
        rows = [dict(zip(columns, row)) for row in result.fetchall()]
        return rows, columns
