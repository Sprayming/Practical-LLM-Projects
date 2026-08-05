import json
import hashlib
from typing import Optional, Any
from loguru import logger
import time


class MemoryCache:
    """内存缓存实现"""
    
    def __init__(self, max_size: int = 1000, default_ttl: int = 300):
        """
        初始化内存缓存
        
        Args:
            max_size: 最大缓存条目数
            default_ttl: 默认过期时间（秒）
        """
        self.cache = {}
        self.max_size = max_size
        self.default_ttl = default_ttl
        self.hits = 0
        self.misses = 0
    
    def get(self, key: str) -> Optional[Any]:
        """获取缓存值"""
        if key in self.cache:
            item = self.cache[key]
            if time.time() < item["expires_at"]:
                self.hits += 1
                return item["value"]
            else:
                # 过期，删除
                del self.cache[key]
        
        self.misses += 1
        return None
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None):
        """设置缓存值"""
        # 检查容量
        if len(self.cache) >= self.max_size:
            self._evict()
        
        ttl = ttl or self.default_ttl
        self.cache[key] = {
            "value": value,
            "expires_at": time.time() + ttl,
            "created_at": time.time()
        }
    
    def delete(self, key: str):
        """删除缓存"""
        if key in self.cache:
            del self.cache[key]
    
    def clear(self):
        """清空缓存"""
        self.cache.clear()
    
    def _evict(self):
        """淘汰过期和最旧的缓存"""
        # 先删除过期的
        now = time.time()
        expired_keys = [k for k, v in self.cache.items() if v["expires_at"] < now]
        for key in expired_keys:
            del self.cache[key]
        
        # 如果还是满的，删除最旧的
        if len(self.cache) >= self.max_size:
            oldest_key = min(self.cache.keys(), key=lambda k: self.cache[k]["created_at"])
            del self.cache[oldest_key]
    
    def get_stats(self) -> dict:
        """获取缓存统计"""
        total = self.hits + self.misses
        return {
            "size": len(self.cache),
            "max_size": self.max_size,
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": round(self.hits / total * 100, 2) if total > 0 else 0
        }


class QueryCache:
    """查询结果缓存"""
    
    def __init__(self, max_size: int = 500, default_ttl: int = 600):
        """
        初始化查询缓存
        
        Args:
            max_size: 最大缓存条目数
            default_ttl: 默认过期时间（秒），默认10分钟
        """
        self.cache = MemoryCache(max_size=max_size, default_ttl=default_ttl)
    
    def _generate_key(self, question: str, **kwargs) -> str:
        """生成缓存键"""
        # 标准化问题
        normalized = question.strip().lower()
        # 添加可选参数
        for k, v in sorted(kwargs.items()):
            normalized += f":{k}={v}"
        # 生成哈希
        return f"query:{hashlib.md5(normalized.encode()).hexdigest()}"
    
    def get(self, question: str, **kwargs) -> Optional[dict]:
        """获取查询结果缓存"""
        key = self._generate_key(question, **kwargs)
        return self.cache.get(key)
    
    def set(self, question: str, result: dict, **kwargs):
        """设置查询结果缓存"""
        key = self._generate_key(question, **kwargs)
        self.cache.set(key, result)
    
    def invalidate(self, question: str, **kwargs):
        """使缓存失效"""
        key = self._generate_key(question, **kwargs)
        self.cache.delete(key)
    
    def clear(self):
        """清空所有查询缓存"""
        self.cache.clear()
    
    def get_stats(self) -> dict:
        """获取缓存统计"""
        return self.cache.get_stats()


# 全局缓存实例
query_cache = QueryCache(max_size=500, default_ttl=600)


def cached_query(ttl: int = 600):
    """查询缓存装饰器"""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            # 获取问题参数
            question = kwargs.get("question") or (args[0] if args else "")
            
            # 尝试从缓存获取
            cached = query_cache.get(question)
            if cached:
                logger.debug("查询缓存命中: {}", question[:50])
                return cached
            
            # 执行查询
            result = await func(*args, **kwargs)
            
            # 缓存结果
            if result:
                query_cache.set(question, result, ttl=ttl)
            
            return result
        return wrapper
    return decorator