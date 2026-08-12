"""
app/memory/redis_client.py —— 短期/中期记忆的 Redis 客户端（含内存回退）

【作用与功能】
为 MemorySystem 提供短期记忆（最近对话，Redis 列表，TTL 2h）与中期记忆（会话摘要，
Redis 字符串，TTL 24h）的存储能力。Redis 不可用时自动降级为内存回退（由调用方
处理），从而保证服务在缓存缺失场景仍可运行。所有键以 `memory:{session_id}:*`
前缀命名，按会话隔离。

【主要组成】
- `RedisClient`：Redis 封装类，提供 is_available / add_short_term /
  get_short_term / set_mid_term / get_mid_term / clear_session

【适用场景】
- 场景1：MemorySystem 同步写入/读取短期与中期记忆时调用
- 场景2：会话重置时调用 clear_session 批量清理该会话所有键

【依赖关系】
- 上游调用方：app.memory.memory_manager（MemorySystem）
- 下游依赖：redis 库（可选，缺失则退化）；TTL 来源于环境变量
"""

"""
Redis 客户端 - 短期/中期记忆存储（自动 TTL 过期 + 内存回退）
"""
import json, os
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class RedisClient:
    """
    Redis 客户端封装：负责短期/中期记忆的读写与自动过期。

    设计要点：
    - 通过 `redis.from_url` 建立连接，连接失败（含 ping 超时）时 `_client` 置为
      None，表示进入内存回退模式；所有公开方法在 `_client` 为 None 时安全降级。
    - 短期记忆使用 Redis List（LPUSH + LTRIM）保留最近 N 条，并设 TTL。
    - 中期记忆使用 Redis String（SET + EX）保存会话摘要，并设 TTL。
    - 键命名统一为 `memory:{session_id}:short` / `memory:{session_id}:mid`。
    """

    def __init__(self, redis_url: Optional[str] = None):
        """
        初始化 Redis 客户端
        
        参数:
            redis_url (Optional[str]): Redis 连接 URL，如果未提供则从环境变量 REDIS_URL 获取，
                                     默认为 "redis://localhost:6379/0"
        """
        self._client = None  # Redis 客户端实例
        if redis_url is None:
            redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        try:
            import redis
            self._client = redis.from_url(redis_url, socket_timeout=2)  # 创建 Redis 客户端，设置2秒超时
            self._client.ping()  # 测试连接是否正常
            logger.info("Redis 连接成功")
        except Exception as e:
            logger.warning(f"Redis 不可用，使用内存回退: {e}")
            self._client = None  # 连接失败时设置为 None，使用内存回退方案

    def is_available(self) -> bool:
        """
        检查 Redis 客户端是否可用
        
        返回:
            bool: 如果 Redis 客户端可用返回 True，否则返回 False
        """
        return self._client is not None

    def add_short_term(self, session_id: str, role: str, content: str) -> bool:
        """
        添加短期记忆（TTL 自动过期）
        
        参数:
            session_id (str): 会话ID，用于区分不同用户的记忆
            role (str): 消息角色（如 "user"、"assistant" 等）
            content (str): 消息内容
            
        返回:
            bool: 成功添加返回 True，Redis 不可用时返回 False
            
        实现细节:
            - 使用列表结构存储消息
            - 使用 LPUSH 将最新消息添加到列表头部
            - 使用 LTRIM 只保留最新的 20 条消息
            - 设置过期时间（默认 7200 秒/2小时）
        """
        if not self._client:
            return False
        key = f"memory:{session_id}:short"  # 构建存储键名
        msg = json.dumps({"role": role, "content": content}, ensure_ascii=False)  # 序列化消息
        self._client.lpush(key, msg)  # 添加到列表头部
        self._client.ltrim(key, 0, 19)  # 只保留最新的20条消息
        self._client.expire(key, int(os.getenv("MEMORY_SHORT_TTL", "7200")))  # 设置过期时间
        return True

    def get_short_term(self, session_id: str, n: int = 6) -> list:
        """
        获取最近 N 条短期记忆
        
        参数:
            session_id (str): 会话ID
            n (int): 要获取的消息数量，默认为6
            
        返回:
            list: 包含最近 N 条消息的列表，每条消息是包含 role 和 content 的字典
                  Redis 不可用时返回空列表
                  
        实现细节:
            - 使用 LRange 获取列表中的元素
            - 反序列化 JSON 数据
        """
        if not self._client:
            return []
        items = self._client.lrange(f"memory:{session_id}:short", 0, n - 1)  # 获取列表中的元素
        return [json.loads(i) for i in items]  # 反序列化 JSON 数据

    def set_mid_term(self, session_id: str, summary: str) -> bool:
        """
        保存中期记忆摘要
        
        参数:
            session_id (str): 会话ID
            summary (str): 会话摘要内容
            
        返回:
            bool: 成功保存返回 True，Redis 不可用时返回 False
            
        实现细节:
            - 使用字符串结构存储摘要
            - 设置过期时间（默认 86400 秒/24小时）
        """
        if not self._client:
            return False
        key = f"memory:{session_id}:mid"  # 构建存储键名
        self._client.set(key, summary, ex=int(os.getenv("MEMORY_MID_TTL", "86400")))  # 设置值并指定过期时间
        return True

    def get_mid_term(self, session_id: str) -> str:
        """
        获取中期记忆
        
        参数:
            session_id (str): 会话ID
            
        返回:
            str: 会话摘要内容，如果不存在或 Redis 不可用返回空字符串
        """
        if not self._client:
            return ""
        val = self._client.get(f"memory:{session_id}:mid")  # 获取存储的值
        return val.decode() if val else ""  # 返回解码后的字符串，如果不存在返回空字符串

    def clear_session(self, session_id: str) -> None:
        """
        清除会话的所有记忆
        
        参数:
            session_id (str): 要清除的会话ID
            
        实现细节:
            - 使用 KEYS 命令查找该会话的所有相关键
            - 使用 DELETE 命令批量删除找到的键
        """
        if not self._client:
            return
        keys = self._client.keys(f"memory:{session_id}:*")  # 查找该会话的所有相关键
        if keys:  # 如果找到键则删除
            self._client.delete(*keys)
