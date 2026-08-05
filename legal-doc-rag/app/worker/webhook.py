"""
Webhook Notification System for Legal-DOC-RAG.

Provides:
- Webhook configuration management
- Event triggering
- Multiple notification channels
- Retry mechanism
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

# 失败 Webhook 的最大发送次数（含首次触发），达到后不再重试
MAX_RETRIES = 5


def _db_path() -> str:
    """返回 webhooks.db 的路径"""
    base = Path(__file__).resolve().parent.parent.parent
    db_dir = base / "tenant_data"
    db_dir.mkdir(parents=True, exist_ok=True)
    return str(db_dir / "webhooks.db")


def _init_db():
    """初始化Webhook数据库表"""
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
    """Webhook管理器"""

    def __init__(self):
        _init_db()
        self._lock = threading.Lock()
        self._retry_thread = None
        self._running = False

    def start(self):
        """启动Webhook管理器"""
        self._running = True
        self._retry_thread = threading.Thread(target=self._retry_loop, daemon=True)
        self._retry_thread.start()
        logger.info("Webhook manager started")

    def stop(self):
        """停止Webhook管理器"""
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
        """
        创建Webhook

        Args:
            tenant_id: 租户ID
            name: Webhook名称
            url: Webhook URL
            events: 触发事件列表
            secret: 签名密钥（可选）

        Returns:
            (成功, 消息, Webhook ID)
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
        """列出Webhook"""
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
        """更新Webhook"""
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
        """删除Webhook"""
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
        """
        触发事件

        Args:
            tenant_id: 租户ID
            event_type: 事件类型
            payload: 事件数据

        Returns:
            触发的Webhook数量
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
        """发送Webhook"""
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
        """重试失败的 Webhook：每 60 秒检查一次，调用 _retry_failed 重发"""
        while self._running:
            try:
                time.sleep(60)  # 每 60 秒检查一次
                self._retry_failed()
            except Exception as e:
                logger.error("Retry loop error: {}", e)

    def _retry_failed(self):
        """重发所有未成功且未超过最大发送次数的 Webhook 日志。"""
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
            # 重新读取 webhook 的 url/secret（可能被更新或删除）
            conn = sqlite3.connect(_db_path())
            try:
                row = conn.execute(
                    "SELECT url, secret FROM webhooks WHERE id = ?", (webhook_id,)
                ).fetchone()
            finally:
                conn.close()

            if not row:
                # webhook 已删除：将该日志置为最大次数，停止重试
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

            # 递增重试计数（达到 MAX_RETRIES 后下一轮不再选中）
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

            # 复用统一发送逻辑（含签名与日志更新）
            self._send_webhook(log_id, webhook_id, url, secret, event_type, payload)

    def get_webhook_logs(
        self,
        webhook_id: int,
        tenant_id: str,
        limit: int = 50,
    ) -> List[Dict]:
        """获取Webhook日志"""
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
    """获取Webhook管理器单例"""
    global _webhook_manager
    if _webhook_manager is None:
        _webhook_manager = WebhookManager()
    return _webhook_manager


# 事件类型常量
class WebhookEvents:
    """Webhook事件类型"""
    DOCUMENT_UPLOADED = "document.uploaded"
    DOCUMENT_DELETED = "document.deleted"
    CHAT_COMPLETED = "chat.completed"
    USER_REGISTERED = "user.registered"
    USER_DELETED = "user.deleted"
    EXPERIMENT_STARTED = "experiment.started"
    EXPERIMENT_STOPPED = "experiment.stopped"
    SYSTEM_ERROR = "system.error"