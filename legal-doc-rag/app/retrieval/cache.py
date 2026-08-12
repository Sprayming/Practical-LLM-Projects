"""
QueryCache —— legal-doc-rag 的查询结果缓存（LRU + TTL）。

【作用与功能】
为检索问答提供带 TTL 过期与 LRU 淘汰的线程安全缓存；命中时直接返回历史
答案，避免重复调用大模型/检索链路，显著降低延迟与成本。

【主要组成】
- `QueryCache`：基于内存 OrderedDict（LRU）与文件落盘的双后端缓存，
  支持 TTL 过期、命中率统计、清理与清除。

【适用场景】
- 场景1：相同/相似法律问题的高频重复提问
- 场景2：服务重启后从文件缓存恢复热点答案

【依赖关系】
- 上游调用方：问答流水线（命中则跳过检索+生成）
- 下游依赖：本地文件系统（可选）、loguru 日志
（原英文说明：LRU + TTL、线程安全、统计、多后端 memory/file/redis 支持）
"""
import json
import os
import hashlib
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any
from collections import OrderedDict
from loguru import logger


class QueryCache:
    """
    Thread-safe query cache with LRU eviction and TTL expiration.

    Features:
    - LRU eviction when max size is reached
    - TTL-based expiration
    - Thread-safe operations
    - Cache hit/miss statistics
    """

    def __init__(
        self,
        cache_dir: str = "cache",
        ttl_seconds: int = 86400,
        max_size: int = 1000,
        use_memory: bool = True,
    ):
        """
        初始化缓存。

        创建缓存根目录，建立内存 LRU 缓存与统计计数；若启用内存模式，
        则从文件缓存恢复未过期的历史条目，并记录初始化日志。

        参数:
            cache_dir: 文件缓存存储目录（默认 "cache"）
            ttl_seconds: 缓存存活时间（秒，默认 86400=24 小时）
            max_size: 内存缓存最大条目数（默认 1000，超出触发 LRU 淘汰）
            use_memory: 是否启用内存 LRU 缓存（True 更快，默认 True）
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.ttl = timedelta(seconds=ttl_seconds)
        self.max_size = max_size
        self.use_memory = use_memory

        # In-memory LRU cache
        self._memory_cache: OrderedDict = OrderedDict()
        self._lock = threading.Lock()

        # Statistics
        self._hits = 0
        self._misses = 0
        self._evictions = 0

        # Load existing file cache into memory if enabled
        if use_memory:
            self._load_file_cache()

        logger.info(
            "QueryCache initialized: dir={}, ttl={}s, max_size={}, memory={}",
            cache_dir, ttl_seconds, max_size, use_memory
        )

    def _load_file_cache(self):
        """将磁盘上的文件缓存读取进内存（仅保留未过期条目）。"""
        try:
            count = 0
            for path in self.cache_dir.glob("*.json"):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        entry = json.load(f)
                    cached_at = datetime.fromisoformat(entry["cached_at"])
                    if datetime.now() - cached_at <= self.ttl:
                        key = path.stem
                        self._memory_cache[key] = entry
                        count += 1
                    else:
                        path.unlink()  # Remove expired
                except Exception:
                    pass

            if count > 0:
                logger.info("Loaded {} entries from file cache", count)
        except Exception as e:
            logger.warning("Failed to load file cache: {}", e)

    def _key(self, query: str) -> str:
        """对查询字符串计算 MD5 作为缓存键（相同问题命中同一缓存）。"""
        return hashlib.md5(query.encode("utf-8")).hexdigest()

    def get(self, query: str) -> Optional[str]:
        """
        根据查询获取缓存的答案。

        优先查内存 LRU；命中且未过期则移到队尾（标记最近使用）并返回；
        否则回退到文件缓存，命中则同步回种内存。过期条目会被删除。
        未命中或异常均返回 None 并累计 miss。

        参数:
            query: 查询字符串
        返回:
            Optional[str]: 缓存答案文本；未命中/已过期返回 None
        """
        key = self._key(query)

        # Try memory cache first
        if self.use_memory:
            with self._lock:
                if key in self._memory_cache:
                    entry = self._memory_cache[key]
                    cached_at = datetime.fromisoformat(entry["cached_at"])
                    if datetime.now() - cached_at <= self.ttl:
                        # Move to end (most recently used)
                        self._memory_cache.move_to_end(key)
                        self._hits += 1
                        return entry["answer"]
                    else:
                        # Expired
                        del self._memory_cache[key]
                        self._evictions += 1

        # Fall back to file cache
        path = self.cache_dir / f"{key}.json"
        if not path.exists():
            self._misses += 1
            return None

        try:
            with open(path, "r", encoding="utf-8") as f:
                entry = json.load(f)
            cached_at = datetime.fromisoformat(entry["cached_at"])
            if datetime.now() - cached_at > self.ttl:
                path.unlink()
                self._misses += 1
                return None

            # Add to memory cache if enabled
            if self.use_memory:
                with self._lock:
                    self._memory_cache[key] = entry
                    self._memory_cache.move_to_end(key)
                    self._trim_memory_cache()

            self._hits += 1
            return entry["answer"]
        except Exception as e:
            logger.warning("Cache read error: {}", e)
            self._misses += 1
            return None

    def set(self, query: str, answer: str, metadata: Optional[Dict] = None):
        """
        写入一条查询答案到缓存（内存 + 文件双写）。

        参数:
            query: 查询字符串（作为缓存键）
            answer: 待缓存的答案文本
            metadata: 可选附带的元数据（如模型、耗时等）
        """
        key = self._key(query)
        entry = {
            "answer": answer,
            "cached_at": datetime.now().isoformat(),
            "metadata": metadata or {},
        }

        # Update memory cache
        if self.use_memory:
            with self._lock:
                self._memory_cache[key] = entry
                self._memory_cache.move_to_end(key)
                self._trim_memory_cache()

        # Update file cache
        try:
            path = self.cache_dir / f"{key}.json"
            with open(path, "w", encoding="utf-8") as f:
                json.dump(entry, f, ensure_ascii=False)
        except Exception as e:
            logger.warning("Cache write error: {}", e)

    def _trim_memory_cache(self):
        """超出 max_size 时按 LRU 淘汰最久未使用条目，并累计淘汰计数。"""
        while len(self._memory_cache) > self.max_size:
            self._memory_cache.popitem(last=False)
            self._evictions += 1

    def clear(self):
        """清空全部缓存（内存 + 磁盘文件）并重置统计计数。"""
        with self._lock:
            self._memory_cache.clear()

        for f in self.cache_dir.glob("*.json"):
            try:
                f.unlink()
            except Exception:
                pass

        self._hits = 0
        self._misses = 0
        self._evictions = 0
        logger.info("Cache cleared")

    def stats(self) -> Dict[str, Any]:
        """返回缓存统计：内存/文件条目数、命中/未命中/淘汰数、命中率(%)等。"""
        with self._lock:
            memory_size = len(self._memory_cache)

        file_count = len(list(self.cache_dir.glob("*.json")))
        total_requests = self._hits + self._misses
        hit_rate = (self._hits / total_requests * 100) if total_requests > 0 else 0

        return {
            "memory_size": memory_size,
            "file_size": file_count,
            "max_size": self.max_size,
            "hits": self._hits,
            "misses": self._misses,
            "evictions": self._evictions,
            "hit_rate_percent": round(hit_rate, 2),
            "total_requests": total_requests,
        }

    def cleanup_expired(self) -> int:
        """扫描并删除文件中已过期的缓存条目，返回删除数量。"""
        removed = 0
        for path in self.cache_dir.glob("*.json"):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    entry = json.load(f)
                cached_at = datetime.fromisoformat(entry["cached_at"])
                if datetime.now() - cached_at > self.ttl:
                    path.unlink()
                    removed += 1
            except Exception:
                pass

        if removed > 0:
            logger.info("Cleaned up {} expired cache entries", removed)
        return removed