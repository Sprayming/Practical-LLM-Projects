"""
app/core/trace_store.py —— 问答 trace 持久化存储（轻量自进化闭环的"经验捕获"层）

【作用与功能】
把每一次问答的完整链路信息落库到本地 SQLite，取代原内存版 TraceStore（重启即丢、不可离线分析）。
落库字段覆盖：用户提问、最终答案、引用来源、各阶段耗时、Token 消耗、使用的 LLM 供应商、
是否命中缓存、是否成功、以及后续回流的用户满意度评分(feedback)。

这是"自进化闭环"的第一环（经验捕获）：所有回答质量信号先沉淀下来，才能做失败归因与
评测回归。法律场景不追求全自动改 prompt，本模块只负责"把原料存好"，是否改进由人工 + 评测
闸门决定。

【主要组成】
- `save_query_trace`:一次问答结束后落库一条记录，返回自增 id。
- `mark_feedback`:用户点赞/点踩时，按租户 + 提问匹配最近一条未反馈记录打标（供失败归因）。
- `get_low_rated` / `get_recent_traces`:离线分析接口，定位"答得差"的样本。
- `export_json`:全量导出，供算法/运营团队离线分析。

【适用场景】
- chat.py 回答生成后调用 save_query_trace 沉淀问答对。
- feedback.py 收到评分时调用 mark_feedback 回流满意度。
- tests/eval/run_eval.py 跑回归时读取历史 trace 做对比。

【依赖关系】
- 仅依赖标准库 sqlite3 / json / threading / time / pathlib，无外部包。
- 数据库文件落在项目根 memory_db/query_traces.db（与现有 memory_db SQLite 模式一致）。
"""

import sqlite3
import json
import threading
import time
from pathlib import Path

# 数据库文件路径：复用项目已有的 memory_db 目录（SQLite 模式）
_DB_PATH = Path(__file__).resolve().parent.parent.parent / "memory_db" / "query_traces.db"
_lock = threading.Lock()  # 保护写操作，避免多 worker 并发写冲突


def _conn():
    """获取一个线程安全的 SQLite 连接（每次新建，避免跨线程共享连接）。"""
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(str(_DB_PATH), timeout=5)


def init_db():
    """初始化数据表（首次调用时建表，已存在则跳过）。"""
    with _lock:
        conn = _conn()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS query_traces (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tenant_id TEXT NOT NULL,
                    query TEXT NOT NULL,
                    answer TEXT,
                    citations TEXT,
                    duration_ms REAL,
                    token_usage INTEGER,
                    provider TEXT,
                    cached INTEGER DEFAULT 0,
                    success INTEGER DEFAULT 1,
                    feedback INTEGER,
                    created_at TEXT NOT NULL
                )
            """)
            conn.commit()
        finally:
            conn.close()


def save_query_trace(
    tenant_id: str,
    query: str,
    answer: str,
    citations: list = None,
    duration_ms: float = 0.0,
    token_usage: int = 0,
    provider: str = "",
    cached: bool = False,
    success: bool = True,
):
    """
    落库一次问答的完整 trace。

    参数:
        tenant_id (str): 租户 id（多租户隔离）。
        query (str): 用户原始提问。
        answer (str): 模型最终回答（已截断以控制体积）。
        citations (list): 引用列表（[{source, content}]），内部 JSON 序列化截断存储。
        duration_ms (float): 端到端耗时（毫秒）。
        token_usage (int): Token 消耗。
        provider (str): 实际命中的 LLM 供应商名（用于 fallback 归因）。
        cached (bool): 是否命中缓存（命中缓存的问答不进入此后处理，故通常 False）。
        success (bool): 是否成功生成（异常路径不调用本函数，故通常 True）。

    返回:
        int: 新插入记录的自增 id；失败返回 -1。
    """
    citations_json = ""
    if citations:
        try:
            citations_json = json.dumps(citations, ensure_ascii=False)[:2000]
        except Exception:
            citations_json = ""
    with _lock:
        conn = _conn()
        try:
            cur = conn.execute(
                """
                INSERT INTO query_traces
                (tenant_id, query, answer, citations, duration_ms, token_usage,
                 provider, cached, success, feedback, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)
                """,
                (
                    tenant_id,
                    query,
                    (answer or "")[:2000],
                    citations_json,
                    duration_ms,
                    token_usage,
                    provider or "",
                    1 if cached else 0,
                    1 if success else 0,
                    time.strftime("%Y-%m-%d %H:%M:%S"),
                ),
            )
            conn.commit()
            return cur.lastrowid
        except Exception as e:
            print(f"[trace_store] save_query_trace 失败: {e}")
            return -1
        finally:
            conn.close()


def mark_feedback(tenant_id: str, query: str, rating: int):
    """
    回流用户满意度评分：按租户 + 提问匹配最近一条"未反馈"记录打标。

    前端目前只传 query（不传 message_id），故用 (tenant_id, query) 精确匹配最近一条
    尚未打分的记录。若同一提问被多次问且已反馈过，则匹配更早未反馈的那条，避免覆盖。

    参数:
        tenant_id (str): 租户 id。
        query (str): 用户原始提问（与落库时一致）。
        rating (int): 评分（1-5，或 -1 表示点踩）。

    返回:
        bool: 是否成功命中并更新一条记录。
    """
    with _lock:
        conn = _conn()
        try:
            cur = conn.execute(
                """
                UPDATE query_traces
                SET feedback = ?
                WHERE id = (
                    SELECT id FROM query_traces
                    WHERE tenant_id = ? AND query = ? AND feedback IS NULL
                    ORDER BY id DESC LIMIT 1
                )
                """,
                (rating, tenant_id, query),
            )
            conn.commit()
            return cur.rowcount > 0
        except Exception as e:
            print(f"[trace_store] mark_feedback 失败: {e}")
            return False
        finally:
            conn.close()


def get_recent_traces(n: int = 20, tenant_id: str = None):
    """获取最近 n 条 trace（可按租户过滤），供运维快速查看。"""
    with _lock:
        conn = _conn()
        try:
            if tenant_id:
                rows = conn.execute(
                    "SELECT * FROM query_traces WHERE tenant_id=? ORDER BY id DESC LIMIT ?",
                    (tenant_id, n),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM query_traces ORDER BY id DESC LIMIT ?", (n,)
                ).fetchall()
            return [_row_to_dict(row) for row in rows]
        finally:
            conn.close()


def get_low_rated(limit: int = 50, tenant_id: str = None):
    """
    取出"答得差"的样本，用于失败归因：满意度 <=2 或生成失败的记录。

    参数:
        limit (int): 最多返回条数。
        tenant_id (str): 可选租户过滤。

    返回:
        list[dict]: 低分/失败样本列表。
    """
    with _lock:
        conn = _conn()
        try:
            sql = (
                "SELECT * FROM query_traces WHERE (feedback IS NOT NULL AND feedback <= 2) "
                "OR success = 0 ORDER BY id DESC LIMIT ?"
            )
            params = [limit]
            if tenant_id:
                sql = (
                    "SELECT * FROM query_traces WHERE tenant_id=? AND "
                    "((feedback IS NOT NULL AND feedback <= 2) OR success = 0) "
                    "ORDER BY id DESC LIMIT ?"
                )
                params = [tenant_id, limit]
            rows = conn.execute(sql, params).fetchall()
            return [_row_to_dict(row) for row in rows]
        finally:
            conn.close()


def export_json(path: str = None, tenant_id: str = None):
    """全量导出 trace 为 JSON 文件，供离线分析。"""
    with _lock:
        conn = _conn()
        try:
            if tenant_id:
                rows = conn.execute(
                    "SELECT * FROM query_traces WHERE tenant_id=? ORDER BY id", (tenant_id,)
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM query_traces ORDER BY id").fetchall()
            data = [_row_to_dict(row) for row in rows]
        finally:
            conn.close()
    if path is None:
        path = str(Path(__file__).resolve().parent.parent.parent / "memory_db" / "query_traces_export.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path


def _row_to_dict(row):
    """把 SQLite 行转成字典（列名来自建表语句）。"""
    cols = ["id", "tenant_id", "query", "answer", "citations", "duration_ms",
            "token_usage", "provider", "cached", "success", "feedback", "created_at"]
    d = dict(zip(cols, row))
    if d.get("citations"):
        try:
            d["citations"] = json.loads(d["citations"])
        except Exception:
            pass
    return d


def get_stats(tenant_id: str = None):
    """
    看板所需的聚合统计指标。

    参数:
        tenant_id (str): 可选租户过滤(传 None 表示全量)。

    返回:
        dict: 总量 / 低分样本数 / 成功数 / 成功率 / 平均延迟 / 反馈数 /
              好评数 / 反馈覆盖率 / 近24h 量 / 供应商分布。
    """
    conds = []
    params = []
    if tenant_id:
        conds.append("tenant_id=?")
        params.append(tenant_id)
    # WHERE 子句(无过滤时为空);where_and 用于在其后追加 AND 条件
    where_clause = (" WHERE " + " AND ".join(conds)) if conds else ""
    where_and = (where_clause + " AND ") if conds else " WHERE "
    with _lock:
        conn = _conn()
        try:
            row = conn.execute(
                f"""
                SELECT COUNT(*),
                       SUM(CASE WHEN (feedback IS NOT NULL AND feedback <= 2) OR success=0 THEN 1 ELSE 0 END),
                       SUM(CASE WHEN success=1 THEN 1 ELSE 0 END),
                       AVG(duration_ms),
                       SUM(CASE WHEN feedback IS NOT NULL THEN 1 ELSE 0 END),
                       SUM(CASE WHEN feedback >= 4 THEN 1 ELSE 0 END)
                FROM query_traces{where_clause}
                """,
                params,
            ).fetchone()
            total, low, succ, avg_dur, fb_cnt, fb_pos = row
            total = total or 0
            low = low or 0
            succ = succ or 0
            fb_cnt = fb_cnt or 0
            fb_pos = fb_pos or 0
            # 近 24h 计数
            since = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() - 86400))
            r24 = conn.execute(
                f"SELECT COUNT(*) FROM query_traces{where_and}created_at >= ?",
                params + [since],
            ).fetchone()[0] or 0
            # 供应商分布
            prov_rows = conn.execute(
                f"SELECT provider, COUNT(*) FROM query_traces{where_clause} GROUP BY provider",
                params,
            ).fetchall()
            provider_dist = {p: c for p, c in prov_rows}
            return {
                "total": total,
                "low_rated": low,
                "success": succ,
                "success_rate": round(succ / total * 100, 1) if total else 0.0,
                "avg_duration_ms": round(avg_dur, 1) if avg_dur else 0.0,
                "feedback_count": fb_cnt,
                "feedback_positive": fb_pos,
                "feedback_coverage": round(fb_cnt / total * 100, 1) if total else 0.0,
                "recent_24h": r24,
                "provider_distribution": provider_dist,
            }
        finally:
            conn.close()


# 模块导入时确保表已存在
init_db()
