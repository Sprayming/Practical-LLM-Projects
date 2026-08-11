"""
A/B Testing Framework for Legal-DOC-RAG.

提供以下功能：
- 实验配置与管理（创建、启动、停止、删除）
- 流量分配（基于权重和用户哈希的确定性分配）
- 事件记录（跟踪用户行为和转化）
- 多变量测试（支持多个变体并行对比）
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
    """
    返回 ab_testing.db 数据库文件的路径。
    
    该函数会自动在项目根目录下的 tenant_data 目录中创建数据库文件。
    
    Returns:
        str: 数据库文件的绝对路径。
    """
    base = Path(__file__).resolve().parent.parent.parent
    db_dir = base / "tenant_data"
    db_dir.mkdir(parents=True, exist_ok=True)
    return str(db_dir / "ab_testing.db")


def _init_db():
    """
    初始化 A/B 测试所需的数据库表。
    
    创建四个核心表：
    1. experiments - 实验主表（名称、描述、状态、流量占比等）
    2. variants - 实验变体表（名称、权重、配置等）
    3. assignments - 用户分配记录表（实验-用户-变体的关联）
    4. events - 事件记录表（用户行为追踪）
    
    所有表都设置了适当的约束和外键关系，确保数据完整性。
    """
    db = _db_path()
    conn = sqlite3.connect(db)
    # 实验主表：存储实验的基本信息和状态
    conn.execute("""
        CREATE TABLE IF NOT EXISTS experiments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            description TEXT,
            status TEXT DEFAULT 'draft',  # draft/active/stopped
            traffic_percent INTEGER DEFAULT 100,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # 变体表：存储每个实验的不同版本配置
    conn.execute("""
        CREATE TABLE IF NOT EXISTS variants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            experiment_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            weight INTEGER DEFAULT 1,  # 权重，用于流量分配比例
            config TEXT,  # JSON 格式的变体配置参数
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (experiment_id) REFERENCES experiments(id) ON DELETE CASCADE,
            UNIQUE(experiment_id, name)  # 同一实验内变体名唯一
        )
    """)
    # 分配表：记录用户被分配到哪个实验的哪个变体
    conn.execute("""
        CREATE TABLE IF NOT EXISTS assignments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            experiment_id INTEGER NOT NULL,
            user_id TEXT NOT NULL,
            variant_id INTEGER NOT NULL,
            assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (experiment_id) REFERENCES experiments(id),
            FOREIGN KEY (variant_id) REFERENCES variants(id),
            UNIQUE(experiment_id, user_id)  # 同一实验内用户只分配一次
        )
    """)
    # 事件表：记录用户在实验中的各种行为
    conn.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            experiment_id INTEGER NOT NULL,
            variant_id INTEGER NOT NULL,
            user_id TEXT,  # 可选，匿名事件可不填
            event_type TEXT NOT NULL,  # 事件类型（如 click, purchase 等）
            event_data TEXT,  # JSON 格式的事件附加数据
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (experiment_id) REFERENCES experiments(id),
            FOREIGN KEY (variant_id) REFERENCES variants(id)
        )
    """)
    conn.commit()
    conn.close()


class ABTestManager:
    """
    A/B 测试管理器核心类。
    
    提供完整的 A/B 测试功能：
    - 实验生命周期管理（创建、启动、停止、删除）
    - 变体管理（添加、权重配置）
    - 流量分配（基于用户哈希的确定性分配）
    - 事件记录与统计分析
    """
    
    def __init__(self):
        """
        初始化 A/B 测试管理器。
        
        执行数据库初始化，并创建线程锁用于保证并发安全。
        """
        _init_db()
        self._lock = threading.Lock()

    def create_experiment(
        self,
        name: str,
        description: str = None,
        traffic_percent: int = 100,
    ) -> Tuple[bool, str, int]:
        """
        创建新的 A/B 测试实验。
        
        Args:
            name (str): 实验名称，必须唯一。
            description (str, optional): 实验描述信息。
            traffic_percent (int, optional): 参与实验的用户流量占比（0-100），默认为 100。
            
        Returns:
            Tuple[bool, str, int]: (是否成功, 消息, 实验ID)。如果名称重复，返回失败和错误信息。
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
        为指定实验添加新的变体。
        
        Args:
            experiment_id (int): 实验 ID。
            name (str): 变体名称，在实验内必须唯一。
            weight (int, optional): 变体权重，用于流量分配比例，默认为 1。
            config (Dict, optional): 变体的自定义配置参数（JSON 格式存储）。
            
        Returns:
            Tuple[bool, str, int]: (是否成功, 消息, 变体ID)。如果名称重复，返回失败和错误信息。
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
        """
        启动指定实验，开始分配流量。
        
        Args:
            experiment_id (int): 要启动的实验 ID。
            
        Returns:
            Tuple[bool, str]: (是否成功, 消息)。如果操作失败，返回错误信息。
        """
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
        """
        停止指定实验，停止分配流量。
        
        Args:
            experiment_id (int): 要停止的实验 ID。
            
        Returns:
            Tuple[bool, str]: (是否成功, 消息)。如果操作失败，返回错误信息。
        """
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
        为用户分配实验变体（核心分配逻辑）。
        
        采用确定性分配策略：
        1. 检查用户是否已分配过变体（避免多次分配）
        2. 检查实验是否处于活跃状态及用户是否在流量范围内
        3. 基于用户 ID 的哈希值进行确定性分配（同一用户始终分配到同一变体）
        4. 根据变体权重按比例分配流量
        
        Args:
            experiment_id (int): 实验 ID。
            user_id (str): 用户唯一标识。
            
        Returns:
            Optional[Dict]: 分配的变体信息字典（包含 variant_id, name, config），
                           如果不符合分配条件则返回 None。
        """
        with self._lock:
            conn = sqlite3.connect(_db_path())
            try:
                # 1. 检查是否已分配过变体
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

                # 2. 检查实验状态和流量范围
                cur = conn.execute(
                    "SELECT status, traffic_percent FROM experiments WHERE id=?",
                    (experiment_id,)
                )
                exp = cur.fetchone()
                if not exp or exp[0] != "active":
                    return None

                traffic_percent = exp[1]

                # 3. 检查用户是否在流量范围内（基于用户哈希）
                user_hash = int(hashlib.md5(f"{experiment_id}:{user_id}".encode()).hexdigest(), 16) % 100
                if user_hash >= traffic_percent:
                    return None

                # 4. 获取所有变体及其权重
                cur = conn.execute(
                    "SELECT id, name, weight, config FROM variants WHERE experiment_id=?",
                    (experiment_id,)
                )
                variants = cur.fetchall()
                if not variants:
                    return None

                # 5. 根据权重选择变体（确定性分配）
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

                # 6. 记录分配结果
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
        记录用户在实验中的行为事件。
        
        Args:
            experiment_id (int): 事件所属的实验 ID。
            variant_id (int): 事件发生的变体 ID。
            event_type (str): 事件类型（如 click, purchase 等）。
            user_id (str, optional): 用户 ID，匿名事件可不填。
            event_data (Dict, optional): 事件的附加数据（JSON 格式）。
            
        Returns:
            bool: 事件记录是否成功。
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
        获取指定实验的统计结果。
        
        返回包含以下信息的字典：
        - 实验基本信息
        - 各变体的用户数和事件数统计
        - 按事件类型和变体的交叉统计
        
        Args:
            experiment_id (int): 要查询的实验 ID。
            
        Returns:
            Dict: 包含实验详细统计结果的数据字典。
        """
        conn = sqlite3.connect(_db_path())
        try:
            # 1. 获取实验基本信息
            cur = conn.execute(
                "SELECT name, description, status, traffic_percent FROM experiments WHERE id=?",
                (experiment_id,)
            )
            exp = cur.fetchone()
            if not exp:
                return {"error": "实验不存在"}

            # 2. 获取各变体的统计信息
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

            # 3. 获取事件类型统计
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
        """
        获取所有实验的列表。
        
        按创建时间倒序返回实验的基本信息。
        
        Returns:
            List[Dict]: 实验列表，每个元素是一个包含实验基本信息的字典。
        """
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
        """
        删除指定实验及其所有相关数据。
        
        采用级联删除策略：
        1. 先删除事件记录
        2. 再删除用户分配记录
        3. 然后删除变体
        4. 最后删除实验本身
        
        Args:
            experiment_id (int): 要删除的实验 ID。
            
        Returns:
            Tuple[bool, str]: (是否成功, 消息)。如果操作失败，返回错误信息。
        """
        conn = sqlite3.connect(_db_path())
        try:
            # 按照依赖关系逆序删除，避免外键约束冲突
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


# 全局单例实例
_ab_manager: Optional[ABTestManager] = None


def get_ab_manager() -> ABTestManager:
    """
    获取 A/B 测试管理器的单例实例。
    
    采用延迟初始化策略，仅在首次调用时创建实例。
    
    Returns:
        ABTestManager: A/B 测试管理器的单例实例。
    """
    global _ab_manager
    if _ab_manager is None:
        _ab_manager = ABTestManager()
    return _ab_manager
