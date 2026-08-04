"""
Query Cache for Legal-DOC-RAG.

Provides:
- LRU cache with TTL expiration
- Thread-safe operations
- Cache statistics
- Multiple backend support (memory, file, Redis)
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
        Initialize the cache.

        Args:
            cache_dir: Directory for file-based cache storage
            ttl_seconds: Time-to-live in seconds (default: 24 hours)
            max_size: Maximum number of cached entries
            use_memory: If True, use in-memory LRU cache (faster)
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
        """Load existing file cache entries into memory."""
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
        """Generate cache key from query."""
        return hashlib.md5(query.encode("utf-8")).hexdigest()

    def get(self, query: str) -> Optional[str]:
        """
        Get cached answer for a query.

        Args:
            query: The query string

        Returns:
            Cached answer or None if not found/expired
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
        Cache an answer for a query.

        Args:
            query: The query string
            answer: The answer to cache
            metadata: Optional metadata to store
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
        """Trim memory cache to max size (LRU eviction)."""
        while len(self._memory_cache) > self.max_size:
            self._memory_cache.popitem(last=False)
            self._evictions += 1

    def clear(self):
        """Clear all cache entries."""
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
        """Get cache statistics."""
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
        """Remove expired entries from file cache. Returns number of removed entries."""
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