import sqlite3
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, List
from loguru import logger

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "query_history.db"


def get_history_db():
    """获取查询历史数据库连接"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_history_db():
    """初始化查询历史数据库表"""
    conn = get_history_db()
    cursor = conn.cursor()
    
    # 创建查询历史表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS query_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question TEXT NOT NULL,
            sql TEXT,
            summary TEXT,
            insight TEXT,
            recommendation TEXT,
            data TEXT,  -- JSON格式存储
            status TEXT DEFAULT 'success',
            error_message TEXT,
            latency_ms REAL,
            tokens_used INTEGER,
            is_favorite BOOLEAN DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # 创建索引
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_query_history_created_at 
        ON query_history(created_at)
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_query_history_status 
        ON query_history(status)
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_query_history_favorite 
        ON query_history(is_favorite)
    """)
    
    conn.commit()
    conn.close()
    logger.info("查询历史数据库初始化完成")


def create_query_history(history: dict) -> Optional[int]:
    """创建查询历史记录"""
    conn = get_history_db()
    cursor = conn.cursor()
    
    try:
        # 将data字段转换为JSON字符串
        data_json = json.dumps(history.get("data"), ensure_ascii=False, default=str) if history.get("data") else None
        
        cursor.execute("""
            INSERT INTO query_history 
            (question, sql, summary, insight, recommendation, data, status, error_message, latency_ms, tokens_used)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            history.get("question"),
            history.get("sql"),
            history.get("summary"),
            history.get("insight"),
            history.get("recommendation"),
            data_json,
            history.get("status", "success"),
            history.get("error_message"),
            history.get("latency_ms"),
            history.get("tokens_used")
        ))
        
        conn.commit()
        history_id = cursor.lastrowid
        logger.info("查询历史记录创建成功: id={}", history_id)
        return history_id
    except Exception as e:
        logger.error("创建查询历史记录失败: {}", e)
        conn.rollback()
        return None
    finally:
        conn.close()


def get_query_history(history_id: int) -> Optional[dict]:
    """获取单条查询历史"""
    conn = get_history_db()
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT * FROM query_history WHERE id = ?", (history_id,))
        row = cursor.fetchone()
        
        if row:
            return _row_to_dict(row)
        return None
    finally:
        conn.close()


def list_query_history(
    page: int = 1,
    page_size: int = 20,
    status: Optional[str] = None,
    is_favorite: Optional[bool] = None,
    search: Optional[str] = None
) -> tuple[List[dict], int]:
    """列出查询历史"""
    conn = get_history_db()
    cursor = conn.cursor()
    
    try:
        # 构建查询条件
        conditions = []
        params = []
        
        if status:
            conditions.append("status = ?")
            params.append(status)
        
        if is_favorite is not None:
            conditions.append("is_favorite = ?")
            params.append(1 if is_favorite else 0)
        
        if search:
            conditions.append("(question LIKE ? OR summary LIKE ?)")
            params.extend([f"%{search}%", f"%{search}%"])
        
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        
        # 获取总数
        cursor.execute(f"SELECT COUNT(*) FROM query_history WHERE {where_clause}", params)
        total = cursor.fetchone()[0]
        
        # 获取分页数据
        offset = (page - 1) * page_size
        cursor.execute(
            f"SELECT * FROM query_history WHERE {where_clause} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            params + [page_size, offset]
        )
        
        items = [_row_to_dict(row) for row in cursor.fetchall()]
        
        return items, total
    finally:
        conn.close()


def update_query_history(history_id: int, updates: dict) -> bool:
    """更新查询历史"""
    conn = get_history_db()
    cursor = conn.cursor()
    
    try:
        set_clauses = []
        params = []
        
        for key, value in updates.items():
            if key == "data":
                value = json.dumps(value, ensure_ascii=False, default=str) if value else None
            set_clauses.append(f"{key} = ?")
            params.append(value)
        
        params.append(history_id)
        
        cursor.execute(
            f"UPDATE query_history SET {', '.join(set_clauses)} WHERE id = ?",
            params
        )
        
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        logger.error("更新查询历史失败: {}", e)
        conn.rollback()
        return False
    finally:
        conn.close()


def toggle_favorite(history_id: int) -> Optional[bool]:
    """切换收藏状态"""
    conn = get_history_db()
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT is_favorite FROM query_history WHERE id = ?", (history_id,))
        row = cursor.fetchone()
        
        if not row:
            return None
        
        new_status = not bool(row["is_favorite"])
        cursor.execute(
            "UPDATE query_history SET is_favorite = ? WHERE id = ?",
            (1 if new_status else 0, history_id)
        )
        
        conn.commit()
        return new_status
    except Exception as e:
        logger.error("切换收藏状态失败: {}", e)
        conn.rollback()
        return None
    finally:
        conn.close()


def delete_query_history(history_id: int) -> bool:
    """删除查询历史"""
    conn = get_history_db()
    cursor = conn.cursor()
    
    try:
        cursor.execute("DELETE FROM query_history WHERE id = ?", (history_id,))
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        logger.error("删除查询历史失败: {}", e)
        conn.rollback()
        return False
    finally:
        conn.close()


def get_query_stats() -> dict:
    """获取查询统计"""
    conn = get_history_db()
    cursor = conn.cursor()
    
    try:
        stats = {}
        
        # 总查询数
        cursor.execute("SELECT COUNT(*) FROM query_history")
        stats["total_queries"] = cursor.fetchone()[0]
        
        # 成功查询数
        cursor.execute("SELECT COUNT(*) FROM query_history WHERE status = 'success'")
        stats["successful_queries"] = cursor.fetchone()[0]
        
        # 失败查询数
        cursor.execute("SELECT COUNT(*) FROM query_history WHERE status = 'error'")
        stats["failed_queries"] = cursor.fetchone()[0]
        
        # 收藏数
        cursor.execute("SELECT COUNT(*) FROM query_history WHERE is_favorite = 1")
        stats["favorite_queries"] = cursor.fetchone()[0]
        
        # 平均延迟
        cursor.execute("SELECT AVG(latency_ms) FROM query_history WHERE latency_ms IS NOT NULL")
        result = cursor.fetchone()[0]
        stats["avg_latency_ms"] = round(result, 2) if result else 0
        
        # 今日查询数
        cursor.execute("""
            SELECT COUNT(*) FROM query_history 
            WHERE DATE(created_at) = DATE('now')
        """)
        stats["today_queries"] = cursor.fetchone()[0]
        
        return stats
    finally:
        conn.close()


def _row_to_dict(row) -> dict:
    """将数据库行转换为字典"""
    data = dict(row)
    # 解析JSON格式的data字段
    if data.get("data"):
        try:
            data["data"] = json.loads(data["data"])
        except json.JSONDecodeError:
            data["data"] = []
    else:
        data["data"] = []
    return data


# 初始化数据库
init_history_db()