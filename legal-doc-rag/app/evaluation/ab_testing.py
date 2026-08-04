"""
A/B Testing Framework for Legal-DOC-RAG.

Provides:
- Experiment configuration and management
- Traffic allocation
- Result recording
- Multi-variable testing
"""
import json
import hashlib
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from loguru import logger
import threading


def _db_path() -> str:
    """返回 ab_testing.db 的路径"""
    base = Path(__file__).resolve().parent.parent.parent
    db_dir = base / "tenant_data"
    db_dir.mkdir(parents=True, exist_ok=True)
    return str(db_dir / "ab_testing.db")


def _init_db():
    """初始化A/B测试数据库表"""
    db = _db_path()
    conn = sqlite3.connect(db)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS experiments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            description TEXT,
            status TEXT DEFAULT 'draft',
            traffic_percent INTEGER DEFAULT 100,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS variants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            experiment_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            weight INTEGER DEFAULT 1,
            config TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (experiment_id) REFERENCES experiments(id) ON DELETE CASCADE,
            UNIQUE(experiment_id, name)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS assignments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            experiment_id INTEGER NOT NULL,
            user_id TEXT NOT NULL,
            variant_id INTEGER NOT NULL,
            assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (experiment_id) REFERENCES experiments(id),
            FOREIGN KEY (variant_id) REFERENCES variants(id),
            UNIQUE(experiment_id, user_id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            experiment_id INTEGER NOT NULL,
            variant_id INTEGER NOT NULL,
            user_id TEXT,
            event_type TEXT NOT NULL,
            event_data TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (experiment_id) REFERENCES experiments(id),
            FOREIGN KEY (variant_id) REFERENCES variants(id)
        )
    """)
    conn.commit()
    conn.close()


class ABTestManager:
    """A/B测试管理器"""

    def __init__(self):
        _init_db()
        self._lock = threading.Lock()

    def create_experiment(
        self,
        name: str,
        description: str = None,
        traffic_percent: int = 100,
    ) -> Tuple[bool, str, int]:
        """
        创建新实验

        Args:
            name: 实验名称
            description: 实验描述
            traffic_percent: 流量百分比 (0-100)

        Returns:
            (成功, 消息, 实验ID)
        """
        conn = sqlite3.connect(_db_path())
        try:
            cur = conn.execute(
                "INSERT INTO experiments (name, description, traffic_percent) VALUES (?, ?, ?)",
                (name, description, traffic_percent)
            )
            experiment_id = cur.lastrowid
            conn.commit()
            return True, "实验创建成功", experiment_id
        except sqlite3.IntegrityError:
            return False, "实验名称已存在", 0
        except Exception as e:
            conn.rollback()
            return False, str(e), 0
        finally:
            conn.close()

    def add_variant(
        self,
        experiment_id: int,
        name: str,
        weight: int = 1,
        config: Dict = None,
    ) -> Tuple[bool, str, int]:
        """
        添加实验变体

        Args:
            experiment_id: 实验ID
            name: 变体名称
            weight: 权重
            config: 变体配置

        Returns:
            (成功, 消息, 变体ID)
        """
        conn = sqlite3.connect(_db_path())
        try:
            config_json = json.dumps(config) if config else None
            cur = conn.execute(
                "INSERT INTO variants (experiment_id, name, weight, config) VALUES (?, ?, ?, ?)",
                (experiment_id, name, weight, config_json)
            )
            variant_id = cur.lastrowid
            conn.commit()
            return True, "变体添加成功", variant_id
        except sqlite3.IntegrityError:
            return False, "变体名称已存在", 0
        except Exception as e:
            conn.rollback()
            return False, str(e), 0
        finally:
            conn.close()

    def start_experiment(self, experiment_id: int) -> Tuple[bool, str]:
        """启动实验"""
        conn = sqlite3.connect(_db_path())
        try:
            conn.execute(
                "UPDATE experiments SET status='active', updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (experiment_id,)
            )
            conn.commit()
            return True, "实验已启动"
        except Exception as e:
            conn.rollback()
            return False, str(e)
        finally:
            conn.close()

    def stop_experiment(self, experiment_id: int) -> Tuple[bool, str]:
        """停止实验"""
        conn = sqlite3.connect(_db_path())
        try:
            conn.execute(
                "UPDATE experiments SET status='stopped', updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (experiment_id,)
            )
            conn.commit()
            return True, "实验已停止"
        except Exception as e:
            conn.rollback()
            return False, str(e)
        finally:
            conn.close()

    def get_variant_for_user(
        self,
        experiment_id: int,
        user_id: str,
    ) -> Optional[Dict]:
        """
        为用户分配变体

        Args:
            experiment_id: 实验ID
            user_id: 用户ID

        Returns:
            变体字典或None
        """
        with self._lock:
            conn = sqlite3.connect(_db_path())
            try:
                # 检查是否已分配
                cur = conn.execute(
                    """SELECT v.id, v.name, v.config
                       FROM assignments a
                       JOIN variants v ON a.variant_id = v.id
                       WHERE a.experiment_id=? AND a.user_id=?""",
                    (experiment_id, user_id)
                )
                row = cur.fetchone()
                if row:
                    return {
                        "variant_id": row[0],
                        "name": row[1],
                        "config": json.loads(row[2]) if row[2] else {},
                    }

                # 检查实验状态
                cur = conn.execute(
                    "SELECT status, traffic_percent FROM experiments WHERE id=?",
                    (experiment_id,)
                )
                exp = cur.fetchone()
                if not exp or exp[0] != "active":
                    return None

                traffic_percent = exp[1]

                # 检查用户是否在流量范围内
                user_hash = int(hashlib.md5(f"{experiment_id}:{user_id}".encode()).hexdigest(), 16) % 100
                if user_hash >= traffic_percent:
                    return None

                # 获取所有变体
                cur = conn.execute(
                    "SELECT id, name, weight, config FROM variants WHERE experiment_id=?",
                    (experiment_id,)
                )
                variants = cur.fetchall()
                if not variants:
                    return None

                # 根据权重选择变体
                total_weight = sum(v[2] for v in variants)
                if total_weight == 0:
                    return None

                # 使用用户ID的哈希来确定性地选择变体
                variant_hash = int(hashlib.md5(f"{user_id}:{experiment_id}".encode()).hexdigest(), 16) % total_weight
                cumulative = 0
                selected_variant = None
                for v in variants:
                    cumulative += v[2]
                    if variant_hash < cumulative:
                        selected_variant = v
                        break

                if not selected_variant:
                    selected_variant = variants[0]

                # 记录分配
                conn.execute(
                    "INSERT INTO assignments (experiment_id, user_id, variant_id) VALUES (?, ?, ?)",
                    (experiment_id, user_id, selected_variant[0])
                )
                conn.commit()

                return {
                    "variant_id": selected_variant[0],
                    "name": selected_variant[1],
                    "config": json.loads(selected_variant[3]) if selected_variant[3] else {},
                }
            except Exception as e:
                logger.error("Failed to get variant for user: {}", e)
                return None
            finally:
                conn.close()

    def record_event(
        self,
        experiment_id: int,
        variant_id: int,
        event_type: str,
        user_id: str = None,
        event_data: Dict = None,
    ) -> bool:
        """
        记录实验事件

        Args:
            experiment_id: 实验ID
            variant_id: 变体ID
            event_type: 事件类型
            user_id: 用户ID
            event_data: 事件数据

        Returns:
            是否成功
        """
        conn = sqlite3.connect(_db_path())
        try:
            event_data_json = json.dumps(event_data) if event_data else None
            conn.execute(
                "INSERT INTO events (experiment_id, variant_id, user_id, event_type, event_data) VALUES (?, ?, ?, ?, ?)",
                (experiment_id, variant_id, user_id, event_type, event_data_json)
            )
            conn.commit()
            return True
        except Exception as e:
            conn.rollback()
            logger.error("Failed to record event: {}", e)
            return False
        finally:
            conn.close()

    def get_experiment_results(self, experiment_id: int) -> Dict:
        """
        获取实验结果

        Args:
            experiment_id: 实验ID

        Returns:
            实验结果字典
        """
        conn = sqlite3.connect(_db_path())
        try:
            # 获取实验信息
            cur = conn.execute(
                "SELECT name, description, status, traffic_percent FROM experiments WHERE id=?",
                (experiment_id,)
            )
            exp = cur.fetchone()
            if not exp:
                return {"error": "实验不存在"}

            # 获取变体统计
            cur = conn.execute(
                """SELECT v.id, v.name, v.weight,
                          COUNT(DISTINCT a.user_id) as user_count,
                          COUNT(e.id) as event_count
                   FROM variants v
                   LEFT JOIN assignments a ON v.id = a.variant_id
                   LEFT JOIN events e ON v.id = e.variant_id
                   WHERE v.experiment_id=?
                   GROUP BY v.id""",
                (experiment_id,)
            )
            variants = cur.fetchall()

            # 获取事件类型统计
            cur = conn.execute(
                """SELECT e.event_type, v.name, COUNT(*) as count
                   FROM events e
                   JOIN variants v ON e.variant_id = v.id
                   WHERE e.experiment_id=?
                   GROUP BY e.event_type, v.name""",
                (experiment_id,)
            )
            event_stats = cur.fetchall()

            return {
                "experiment": {
                    "name": exp[0],
                    "description": exp[1],
                    "status": exp[2],
                    "traffic_percent": exp[3],
                },
                "variants": [
                    {
                        "id": v[0],
                        "name": v[1],
                        "weight": v[2],
                        "user_count": v[3],
                        "event_count": v[4],
                    }
                    for v in variants
                ],
                "event_stats": [
                    {"event_type": e[0], "variant_name": e[1], "count": e[2]}
                    for e in event_stats
                ],
            }
        finally:
            conn.close()

    def list_experiments(self) -> List[Dict]:
        """列出所有实验"""
        conn = sqlite3.connect(_db_path())
        try:
            cur = conn.execute(
                "SELECT id, name, description, status, traffic_percent, created_at FROM experiments ORDER BY created_at DESC"
            )
            rows = cur.fetchall()
            return [
                {
                    "id": r[0],
                    "name": r[1],
                    "description": r[2],
                    "status": r[3],
                    "traffic_percent": r[4],
                    "created_at": r[5],
                }
                for r in rows
            ]
        finally:
            conn.close()

    def delete_experiment(self, experiment_id: int) -> Tuple[bool, str]:
        """删除实验"""
        conn = sqlite3.connect(_db_path())
        try:
            # 删除相关数据
            conn.execute("DELETE FROM events WHERE experiment_id=?", (experiment_id,))
            conn.execute("DELETE FROM assignments WHERE experiment_id=?", (experiment_id,))
            conn.execute("DELETE FROM variants WHERE experiment_id=?", (experiment_id,))
            conn.execute("DELETE FROM experiments WHERE id=?", (experiment_id,))
            conn.commit()
            return True, "实验删除成功"
        except Exception as e:
            conn.rollback()
            return False, str(e)
        finally:
            conn.close()


# 全局单例
_ab_manager: Optional[ABTestManager] = None


def get_ab_manager() -> ABTestManager:
    """获取A/B测试管理器单例"""
    global _ab_manager
    if _ab_manager is None:
        _ab_manager = ABTestManager()
    return _ab_manager