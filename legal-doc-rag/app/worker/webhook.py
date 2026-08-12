"""
webhook.py —— Legal-DOC-RAG Webhook 通知系统

【作用与功能】
本模块提供基于 SQLite 的 Webhook 订阅与事件推送能力:租户可配置外部回调
地址与关注的事件类型，系统在相应事件发生时异步推送通知，并对失败的推送
进行周期性重试(最多 `MAX_RETRIES` 次)。若未安装 `httpx`，触发与发送
会被安全跳过。

【主要组成】
- `_db_path` / `_init_db`:webhooks.db 路径与表结构(webhooks / webhook_logs)
- `WebhookManager`:增删改查 Webhook、触发事件、发送与重试推送
- `get_webhook_manager()`:获取全局单例
- `WebhookEvents`:事件类型常量

【适用场景】
- 场景1:租户在前台配置 Webhook 订阅(如文档上传完成、对话完成)
- 场景2:业务事件发生时调用 `trigger_event` 异步通知外部系统

【依赖关系】
- 上游调用方:事件触发逻辑、管理后台 Webhook 配置接口
- 下游依赖:sqlite3、httpx(可选)、loguru
"""
import json
import hashlib
import sqlite3
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from loguru import logger

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False

# 失败 Webhook 的最大发送次数(含首次触发)，达到后不再重试
MAX_RETRIES = 5


def _db_path() -> str:
    """返回 webhooks.db 的路径。

    以本文件为基准向上三级定位项目根，在 `tenant_data` 目录下存放
    webhooks.db；若目录不存在则自动创建。

    参数:
        无

    返回:
        str: webhooks.db 的绝对路径

    异常:
        无(目录创建失败时由调用方抛错)
    适用场景:
        - 所有数据库操作前获取统一存储路径
    """
    base = Path(__file__).resolve().parent.parent.parent
    db_dir = base / "tenant_data"
    db_dir.mkdir(parents=True, exist_ok=True)
    return str(db_dir / "webhooks.db")


def _init_db():
    """初始化 Webhook 相关数据库表。

    创建 `webhooks`(订阅配置:租户、名称、URL、密钥、事件、启用状态)与
    `webhook_logs`(发送日志，外键级联删除)两张表。语句均带
    IF NOT EXISTS，可重复安全调用。

    参数:
        无

    返回:
        None

    异常:
        无(sqlite 错误向上抛出，由调用方处理)
    适用场景:
        - `WebhookManager` 实例化时调用，确保表存在
    """
    db = _db_path()
    conn = sqlite3.connect(db)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS webhooks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id TEXT NOT NULL,
            name TEXT NOT NULL,
            url TEXT NOT NULL,
            secret TEXT,
            events TEXT NOT NULL,
            enabled INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS webhook_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            webhook_id INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            payload TEXT,
            response_status INTEGER,
            response_body TEXT,
            success INTEGER DEFAULT 0,
            attempts INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (webhook_id) REFERENCES webhooks(id) ON DELETE CASCADE
        )
    """)
    conn.commit()
    conn.close()


class WebhookManager:
    """Webhook 管理器。

    负责 Webhook 订阅的增删改查、事件触发后的异步推送，以及后台失败重试
    线程的启停。通过 `threading.Lock` 保证单实例内数据库操作的线程安全。
    """

    def __init__(self):
        """初始化管理器并确保数据库表就绪。"""
        _init_db()
        self._lock = threading.Lock()
        self._retry_thread = None
        self._running = False

    def start(self):
        """启动 Webhook 管理器并开启失败重试后台线程。

        置 `_running=True` 后启动守护线程运行 `_retry_loop`，周期性重发
        失败的 Webhook 推送。

        参数:
            无

        返回:
            None

        异常:
            无
        """
        self._running = True
        self._retry_thread = threading.Thread(target=self._retry_loop, daemon=True)
        self._retry_thread.start()
        logger.info("Webhook manager started")

    def stop(self):
        """停止 Webhook 管理器与重试线程。

        置 `_running=False` 并 `join` 重试线程(最多 5 秒)，完成优雅关闭。

        参数:
            无

        返回:
            None

        异常:
            无
        """
        self._running = False
        if self._retry_thread:
            self._retry_thread.join(timeout=5)
        logger.info("Webhook manager stopped")

    def create_webhook(
        self,
        tenant_id: str,
        name: str,
        url: str,
        events: List[str],
        secret: str = None,
    ) -> Tuple[bool, str, int]:
        """创建 Webhook 订阅。

        将租户、名称、回调 URL、签名密钥与关注的事件列表(JSON 序列化)写入
        `webhooks` 表，返回新纪录 id；失败则回滚并返回错误信息。

        参数:
            tenant_id (str): 租户标识(用于隔离订阅)
            name (str): Webhook 名称
            url (str): 回调地址
            events (List[str]): 关注的事件类型列表(如 ["document.uploaded"])
            secret (str, 可选): 用于签名校验的密钥

        返回:
            Tuple[bool, str, int]: (是否成功, 消息, 新建 Webhook 的 id)

        异常:
            无(数据库错误被捕获并以 (False, 错误信息, 0) 返回)
        适用场景:
            - 管理后台新增 Webhook 订阅
        """
        conn = sqlite3.connect(_db_path())
        try:
            events_json = json.dumps(events)
            cur = conn.execute(
                "INSERT INTO webhooks (tenant_id, name, url, secret, events) VALUES (?, ?, ?, ?, ?)",
                (tenant_id, name, url, secret, events_json)
            )
            webhook_id = cur.lastrowid
            conn.commit()
            return True, "Webhook创建成功", webhook_id
        except Exception as e:
            conn.rollback()
            return False, str(e), 0
        finally:
            conn.close()

    def list_webhooks(self, tenant_id: str) -> List[Dict]:
        """列出某租户的全部 Webhook 订阅。

        读取 `webhooks` 表中该租户的记录，将 `events` JSON 反序列化后返回
        字典列表(含 id、名称、URL、事件、启用状态与创建时间)。

        参数:
            tenant_id (str): 租户标识

        返回:
            List[Dict]: Webhook 订阅字典列表

        异常:
            无
        适用场景:
            - 管理后台展示租户的 Webhook 列表
        """
        conn = sqlite3.connect(_db_path())
        try:
            cur = conn.execute(
                "SELECT id, name, url, events, enabled, created_at FROM webhooks WHERE tenant_id=?",
                (tenant_id,)
            )
            rows = cur.fetchall()
            return [
                {
                    "id": r[0],
                    "name": r[1],
                    "url": r[2],
                    "events": json.loads(r[3]),
                    "enabled": bool(r[4]),
                    "created_at": r[5],
                }
                for r in rows
            ]
        finally:
            conn.close()

    def update_webhook(
        self,
        webhook_id: int,
        tenant_id: str,
        name: str = None,
        url: str = None,
        events: List[str] = None,
        enabled: bool = None,
    ) -> Tuple[bool, str]:
        """更新指定 Webhook 订阅的字段。

        先校验 Webhook 存在且属于该租户，再按需更新提供的字段
        (名称/URL/事件/启用状态)，并刷新 `updated_at`。无变更时返回
        「无需更新」。

        参数:
            webhook_id (int): 要更新的 Webhook id
            tenant_id (str): 租户标识(权限校验)
            name (str, 可选): 新名称
            url (str, 可选): 新回调地址
            events (List[str], 可选): 新事件列表
            enabled (bool, 可选): 是否启用

        返回:
            Tuple[bool, str]: (是否成功, 消息)

        异常:
            无(数据库错误被捕获并回滚)
        适用场景:
            - 管理后台修改 Webhook 配置
        """
        conn = sqlite3.connect(_db_path())
        try:
            # Check if webhook exists
            cur = conn.execute(
                "SELECT id FROM webhooks WHERE id=? AND tenant_id=?",
                (webhook_id, tenant_id)
            )
            if not cur.fetchone():
                return False, "Webhook不存在"

            updates = []
            params = []
            if name is not None:
                updates.append("name=?")
                params.append(name)
            if url is not None:
                updates.append("url=?")
                params.append(url)
            if events is not None:
                updates.append("events=?")
                params.append(json.dumps(events))
            if enabled is not None:
                updates.append("enabled=?")
                params.append(1 if enabled else 0)

            if updates:
                updates.append("updated_at=CURRENT_TIMESTAMP")
                params.append(webhook_id)
                conn.execute(
                    f"UPDATE webhooks SET {', '.join(updates)} WHERE id=?",
                    params
                )
                conn.commit()
                return True, "Webhook更新成功"
            return True, "无需更新"
        except Exception as e:
            conn.rollback()
            return False, str(e)
        finally:
            conn.close()

    def delete_webhook(self, webhook_id: int, tenant_id: str) -> Tuple[bool, str]:
        """删除指定 Webhook 订阅。

        按 id 与租户双重条件删除；由于 `webhook_logs` 设置了外键级联删除，
        相关发送日志也会一并清除。返回操作结果。

        参数:
            webhook_id (int): 要删除的 Webhook id
            tenant_id (str): 租户标识(权限校验)

        返回:
            Tuple[bool, str]: (是否成功, 消息)

        异常:
            无
        适用场景:
            - 管理后台移除 Webhook 订阅
        """
        conn = sqlite3.connect(_db_path())
        try:
            conn.execute(
                "DELETE FROM webhooks WHERE id=? AND tenant_id=?",
                (webhook_id, tenant_id)
            )
            conn.commit()
            return True, "Webhook删除成功"
        except Exception as e:
            conn.rollback()
            return False, str(e)
        finally:
            conn.close()

    def trigger_event(
        self,
        tenant_id: str,
        event_type: str,
        payload: Dict,
    ) -> int:
        """触发事件并向匹配的 Webhook 异步推送通知。

        若未安装 `httpx` 则跳过并返回 0。否则查询该租户下启用中的 Webhook，
        凡 `events` 包含当前 `event_type` 或通配符 `*`，便写入一条
        `webhook_logs` 记录并启动独立线程调用 `_send_webhook` 异步发送；
        返回实际触发的 Webhook 数量。

        参数:
            tenant_id (str): 租户标识
            event_type (str): 事件类型(见 `WebhookEvents`)
            payload (Dict): 随事件携带的数据

        返回:
            int: 成功触发的 Webhook 数量

        异常:
            无(数据库/发送异常被捕获并降级为返回 0)
        适用场景:
            - 业务事件(文档上传、对话完成等)发生时调用
        """
        if not HTTPX_AVAILABLE:
            logger.warning("httpx not installed, skipping webhook trigger")
            return 0

        conn = sqlite3.connect(_db_path())
        try:
            # Get matching webhooks
            cur = conn.execute(
                "SELECT id, url, secret, events FROM webhooks WHERE tenant_id=? AND enabled=1",
                (tenant_id,)
            )
            webhooks = cur.fetchall()

            triggered = 0
            for webhook_id, url, secret, events_json in webhooks:
                events = json.loads(events_json)
                if event_type in events or "*" in events:
                    # Log the event
                    payload_json = json.dumps(payload)
                    conn.execute(
                        "INSERT INTO webhook_logs (webhook_id, event_type, payload, attempts) VALUES (?, ?, ?, 1)",
                        (webhook_id, event_type, payload_json)
                    )
                    log_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                    conn.commit()

                    # Send webhook asynchronously
                    threading.Thread(
                        target=self._send_webhook,
                        args=(log_id, webhook_id, url, secret, event_type, payload),
                        daemon=True
                    ).start()
                    triggered += 1

            return triggered
        except Exception as e:
            logger.error("Failed to trigger event: {}", e)
            return 0
        finally:
            conn.close()

    def _send_webhook(
        self,
        log_id: int,
        webhook_id: int,
        url: str,
        secret: str,
        event_type: str,
        payload: Dict,
    ):
        """向单个 Webhook 地址发送一次通知。

        构造请求头(含 `X-Webhook-Event`)，若提供 `secret` 则以
        `sha256(payload + secret)` 生成 `X-Webhook-Signature` 签名；通过
        httpx 发送 JSON 体(含事件、时间戳、数据)，并把响应状态/正文写回
        `webhook_logs`(成功与否)。发送异常同样记录到日志。

        参数:
            log_id (int): 对应的 webhook_logs 记录 id
            webhook_id (int): Webhook id
            url (str): 回调地址
            secret (str): 签名密钥(可为空)
            event_type (str): 事件类型
            payload (Dict): 事件数据

        返回:
            None

        异常:
            无(异常被捕获并写入日志，不向上抛出)
        适用场景:
            - 事件触发与失败重试时复用同一发送逻辑
        """
        try:
            headers = {
                "Content-Type": "application/json",
                "X-Webhook-Event": event_type,
            }

            # Add signature if secret is provided
            if secret:
                payload_str = json.dumps(payload)
                signature = hashlib.sha256((payload_str + secret).encode()).hexdigest()
                headers["X-Webhook-Signature"] = signature

            body = {
                "event": event_type,
                "timestamp": datetime.now().isoformat(),
                "data": payload,
            }

            with httpx.Client(timeout=30) as client:
                response = client.post(url, json=body, headers=headers)

                # Update log
                conn = sqlite3.connect(_db_path())
                try:
                    conn.execute(
                        """UPDATE webhook_logs
                           SET response_status=?, response_body=?, success=?
                           WHERE id=?""",
                        (response.status_code, response.text[:1000], 1 if response.status_code < 400 else 0, log_id)
                    )
                    conn.commit()
                finally:
                    conn.close()

                if response.status_code >= 400:
                    logger.warning("Webhook failed: {} -> {}", url, response.status_code)
                else:
                    logger.debug("Webhook sent: {} -> {}", url, response.status_code)

        except Exception as e:
            logger.error("Webhook error: {} -> {}", url, e)
            # Update log with error
            conn = sqlite3.connect(_db_path())
            try:
                conn.execute(
                    "UPDATE webhook_logs SET response_body=?, success=0 WHERE id=?",
                    (str(e)[:1000], log_id)
                )
                conn.commit()
            finally:
                conn.close()

    def _retry_loop(self):
        """失败 Webhook 重试后台循环。

        在 `start()` 启动的守护线程中运行:每 60 秒调用一次 `_retry_failed`
        重发未成功的推送，直到 `stop()` 将 `_running` 置 False。

        参数:
            无

        返回:
            None

        异常:
            无(单轮异常被捕获并记录，不影响后续循环)
        """
        while self._running:
            try:
                time.sleep(60)  # 每 60 秒检查一次
                self._retry_failed()
            except Exception as e:
                logger.error("Retry loop error: {}", e)

    def _retry_failed(self):
        """重发所有未成功且未超过最大发送次数的 Webhook 日志。

        扫描 `webhook_logs` 中 `success=0` 且 `attempts < MAX_RETRIES` 的记录，
        逐条重新读取对应 Webhook 的 URL/密钥(可能已变更或删除):若 Webhook
        已删除则将其 attempts 置为上限以停止重试；否则先递增 attempts，再
        复用 `_send_webhook` 重新发送。

        参数:
            无

        返回:
            None

        异常:
            无(单条失败被捕获并继续后续)
        适用场景:
            - 由 `_retry_loop` 周期性调用
        """
        conn = sqlite3.connect(_db_path())
        try:
            rows = conn.execute(
                "SELECT id, webhook_id, event_type, payload "
                "FROM webhook_logs WHERE success = 0 AND attempts < ? "
                "ORDER BY created_at ASC",
                (MAX_RETRIES,),
            ).fetchall()
        finally:
            conn.close()

        for log_id, webhook_id, event_type, payload_str in rows:
            # 重新读取 webhook 的 url/secret(可能被更新或删除)
            conn = sqlite3.connect(_db_path())
            try:
                row = conn.execute(
                    "SELECT url, secret FROM webhooks WHERE id = ?", (webhook_id,)
                ).fetchone()
            finally:
                conn.close()

            if not row:
                # webhook 已删除:将该日志置为最大次数，停止重试
                conn = sqlite3.connect(_db_path())
                try:
                    conn.execute(
                        "UPDATE webhook_logs SET attempts = ? WHERE id = ?",
                        (MAX_RETRIES, log_id),
                    )
                    conn.commit()
                finally:
                    conn.close()
                continue

            url, secret = row

            # 递增重试计数(达到 MAX_RETRIES 后下一轮不再选中)
            conn = sqlite3.connect(_db_path())
            try:
                conn.execute(
                    "UPDATE webhook_logs SET attempts = attempts + 1 WHERE id = ?",
                    (log_id,),
                )
                conn.commit()
            finally:
                conn.close()

            try:
                payload = json.loads(payload_str) if payload_str else {}
            except json.JSONDecodeError:
                payload = {}

            # 复用统一发送逻辑(含签名与日志更新)
            self._send_webhook(log_id, webhook_id, url, secret, event_type, payload)

    def get_webhook_logs(
        self,
        webhook_id: int,
        tenant_id: str,
        limit: int = 50,
    ) -> List[Dict]:
        """获取指定 Webhook 的发送日志(按时间倒序)。

        先校验 Webhook 属于该租户(防越权)，再读取最近的 `limit` 条日志，
        返回含事件类型、响应状态、成功标记与重试次数的字典列表。

        参数:
            webhook_id (int): Webhook id
            tenant_id (str): 租户标识(权限校验)
            limit (int): 返回条数上限，默认 50

        返回:
            List[Dict]: 发送日志字典列表；校验不通过返回空列表

        异常:
            无
        适用场景:
            - 管理后台查看某 Webhook 的推送历史与成功率
        """
        conn = sqlite3.connect(_db_path())
        try:
            # Verify webhook belongs to tenant
            cur = conn.execute(
                "SELECT id FROM webhooks WHERE id=? AND tenant_id=?",
                (webhook_id, tenant_id)
            )
            if not cur.fetchone():
                return []

            cur = conn.execute(
                """SELECT id, event_type, response_status, success, attempts, created_at
                   FROM webhook_logs
                   WHERE webhook_id=?
                   ORDER BY created_at DESC
                   LIMIT ?""",
                (webhook_id, limit)
            )
            rows = cur.fetchall()
            return [
                {
                    "id": r[0],
                    "event_type": r[1],
                    "response_status": r[2],
                    "success": bool(r[3]),
                    "attempts": r[4],
                    "created_at": r[5],
                }
                for r in rows
            ]
        finally:
            conn.close()


# 全局单例
_webhook_manager: Optional[WebhookManager] = None


def get_webhook_manager() -> WebhookManager:
    """获取全局单例 Webhook 管理器(懒初始化)。

    首次调用时创建 `WebhookManager` 实例并复用，保证全应用共享同一管理器
    与数据库锁。

    参数:
        无

    返回:
        WebhookManager: 全局唯一的 Webhook 管理器实例

    异常:
        无
    适用场景:
        - 应用启动与各处触发事件时统一获取实例
    """
    global _webhook_manager
    if _webhook_manager is None:
        _webhook_manager = WebhookManager()
    return _webhook_manager


# 事件类型常量
class WebhookEvents:
    """Webhook 事件类型常量。

    集中定义系统可触发的事件名，供 `trigger_event` 与 Webhook 订阅的 `events`
    列表引用，避免散落字符串拼写错误。
    """
    DOCUMENT_UPLOADED = "document.uploaded"
    DOCUMENT_DELETED = "document.deleted"
    CHAT_COMPLETED = "chat.completed"
    USER_REGISTERED = "user.registered"
    USER_DELETED = "user.deleted"
    EXPERIMENT_STARTED = "experiment.started"
    EXPERIMENT_STOPPED = "experiment.stopped"
    SYSTEM_ERROR = "system.error"