# =+= NEW MODULE - Added 2026-07-14 by Codex =+=

"""
Redis 客户端 - 短期/中期记忆存储（自动 TTL 过期 + 内存回退）
"""
import json, os
from typing import Optional


class RedisClient:
    def __init__(self, redis_url: Optional[str] = None):
        self._client = None
        if redis_url is None:
            redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        try:
            import redis
            self._client = redis.from_url(redis_url, socket_timeout=2)
            self._client.ping()
            print("Redis 连接成功")
        except Exception as e:
            print(f"Redis 不可用，使用内存回退: {e}")
            self._client = None

    def is_available(self):
        return self._client is not None

    def add_short_term(self, session_id: str, role: str, content: str):
        """添加短期记忆（TTL 自动过期）"""
        if not self._client:
            return False
        key = f"memory:{session_id}:short"
        msg = json.dumps({"role": role, "content": content}, ensure_ascii=False)
        self._client.lpush(key, msg)
        self._client.ltrim(key, 0, 19)
        self._client.expire(key, int(os.getenv("MEMORY_SHORT_TTL", "7200")))
        return True

    def get_short_term(self, session_id: str, n: int = 6) -> list:
        """获取最近 N 条短期记忆"""
        if not self._client:
            return []
        items = self._client.lrange(f"memory:{session_id}:short", 0, n - 1)
        return [json.loads(i) for i in items]

    def set_mid_term(self, session_id: str, summary: str):
        """保存中期记忆摘要"""
        if not self._client:
            return False
        key = f"memory:{session_id}:mid"
        self._client.set(key, summary, ex=int(os.getenv("MEMORY_MID_TTL", "86400")))
        return True

    def get_mid_term(self, session_id: str) -> str:
        """获取中期记忆"""
        if not self._client:
            return ""
        val = self._client.get(f"memory:{session_id}:mid")
        return val.decode() if val else ""

    def clear_session(self, session_id: str):
        """清除会话的所有记忆"""
        if not self._client:
            return
        keys = self._client.keys(f"memory:{session_id}:*")
        if keys:
            self._client.delete(*keys)