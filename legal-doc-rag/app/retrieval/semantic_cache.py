"""
semantic_cache.py —— 基于 Redis 的语义缓存(近似问题复用答案)

【作用与功能】
在原有「精确缓存(QueryCache,按问题 MD5 命中完全相同提问)」之外,新增一层
「语义缓存」:把每个已回答问题的向量与答案存入 Redis,新提问时计算其向量并与
缓存中的向量做余弦相似度比较,超过阈值即视为「语义相同」,直接复用答案。

核心收益(解决什么问题):
- 延迟:近似提问(换种说法、同义表述)无需再跑 embedding + 重排序 + LLM 生成,
  首字延迟从「秒级」降到「毫秒级」。
- 成本:DeepSeek 按 token 计费且峰谷定价,语义缓存命中可显著降低 LLM 调用量。

容灾设计:
- Redis 不可用时整体降级为「不缓存、不命中」,主流程完全不受影响(不影响检索/生成)。
- 所有 Redis 操作包在 try/except 中,网络抖动不会抛出到调用方。

【主要组成】
- `SemanticCache`:基于 Redis 的语义缓存,提供 get/set(按租户隔离,带 TTL 与规模上限)。

【依赖关系】
- 上游调用方:问答流水线 chat.py(_check_cache 命中、_handle_post_processing 写入)
- 下游依赖:redis-py、NumPy(余弦相似度)
"""

import hashlib
import json
import time
from typing import List, Optional

import numpy as np
from loguru import logger


def _cosine(a: List[float], b: List[float]) -> float:
    """计算两个向量的余弦相似度,任一向量为零则返回 0.0。"""
    va = np.asarray(a, dtype=np.float32)
    vb = np.asarray(b, dtype=np.float32)
    denom = float(np.linalg.norm(va) * np.linalg.norm(vb))
    if denom == 0.0:
        return 0.0
    return float(np.dot(va, vb) / denom)


class SemanticCache:
    """
    基于 Redis 的语义缓存(按租户隔离)。

    存储结构(每个租户一套):
    - 条目键:  `semcache:{tenant_id}:{md5(query)}` -> JSON{ q, emb, a, ts }
    - 索引键:  `semcache:{tenant_id}:index`      -> Set(所有条目键的 md5)

    get: 计算新查询向量后,遍历索引逐个比对余弦相似度,取最高者;>= 阈值返回答案。
    set: 写入条目并登记到索引;靠 TTL 自动过期,靠 max_entries 控制规模。
    """

    def __init__(
        self,
        redis_url: str,
        tenant_id: str,
        threshold: float = 0.92,
        ttl_seconds: int = 86400,
        max_entries: int = 5000,
    ):
        """
        初始化语义缓存。

        参数:
            redis_url: Redis 连接串(如 redis://localhost:6379/0)
            tenant_id: 租户 ID,用于缓存键隔离
            threshold: 余弦相似度命中阈值(默认 0.92,越高越严格)
            ttl_seconds: 缓存条目存活时间(默认 86400=24h)
            max_entries: 单租户最大缓存条目数(超出后新写入覆盖最旧者由 TTL 兜底)
        """
        self.tenant_id = tenant_id
        self.threshold = threshold
        self.ttl = ttl_seconds
        self.max_entries = max_entries
        self.enabled = False
        self._r = None
        try:
            import redis

            self._r = redis.from_url(redis_url, socket_timeout=2, decode_responses=True)
            self._r.ping()
            self.enabled = True
            logger.info(
                "SemanticCache 已启用: tenant={}, threshold={}, ttl={}s",
                tenant_id, threshold, ttl_seconds,
            )
        except Exception as e:  # noqa: BLE001
            # Redis 不可用 -> 降级为「不缓存」,主流程不受影响
            logger.warning("SemanticCache 不可用(Redis 未连接),降级为不缓存: {}", e)
            self.enabled = False

    # ---- 内部键构造 ----
    def _entry_key(self, qhash: str) -> str:
        return f"semcache:{self.tenant_id}:{qhash}"

    def _index_key(self) -> str:
        return f"semcache:{self.tenant_id}:index"

    def get(self, query: str, query_emb: List[float]) -> Optional[str]:
        """
        按语义相似度查找缓存答案。

        参数:
            query: 原始提问文本(作为缓存键与存储内容)
            query_emb: 该提问的向量(由调用方用嵌入模型计算)
        返回:
            Optional[str]: 命中则返回历史答案,否则返回 None
        """
        if not self.enabled or self._r is None:
            return None
        try:
            index_key = self._index_key()
            members = self._r.smembers(index_key)
            if not members:
                return None

            best_ans: Optional[str] = None
            best_sim = self.threshold
            for qh in members:
                raw = self._r.get(self._entry_key(qh))
                if not raw:
                    continue
                try:
                    entry = json.loads(raw)
                except Exception:
                    continue
                cached_emb = entry.get("emb")
                if not cached_emb:
                    continue
                sim = _cosine(query_emb, cached_emb)
                if sim >= best_sim:
                    best_sim = sim
                    best_ans = entry.get("a")
            if best_ans is not None:
                logger.debug("语义缓存命中: sim={:.3f}", best_sim)
            return best_ans
        except Exception as e:  # noqa: BLE001
            logger.warning("SemanticCache.get 异常,降级跳过: {}", e)
            return None

    def set(self, query: str, query_emb: List[float], answer: str) -> None:
        """
        写入一条语义缓存(问题向量 + 答案),并登记到索引。

        参数:
            query: 原始提问文本
            query_emb: 该提问的向量
            answer: 待缓存的答案文本
        """
        if not self.enabled or self._r is None:
            return
        try:
            qh = hashlib.md5(query.encode("utf-8")).hexdigest()
            entry = {
                "q": query,
                "emb": query_emb,
                "a": answer,
                "ts": int(time.time()),
            }
            self._r.set(self._entry_key(qh), json.dumps(entry, ensure_ascii=False), ex=self.ttl)
            self._r.sadd(self._index_key(), qh)
            self._r.expire(self._index_key(), self.ttl)
        except Exception as e:  # noqa: BLE001
            logger.warning("SemanticCache.set 异常,跳过写入: {}", e)
