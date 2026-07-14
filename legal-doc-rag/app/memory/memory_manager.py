"""
三层记忆系统 - Redis + ChromaDB + 异步持久化 + 距离阈值
短 期：Redis List（TTL 2h），回退：内存列表
中 期：Redis String（TTL 24h），回退：内存字符串
长 期：ChromaDB 向量检索（相似度阈值过滤）
异步持久化：后台线程自动将短期→中期→长期归档
"""
import json, uuid, os, threading
from datetime import datetime
from typing import Callable, Optional
from langchain_chroma import Chroma
from loguru import logger
from app.memory.redis_client import RedisClient


class MemorySystem:
    def __init__(self, embedding_model, persist_dir: str = "./memory_db", redis_url: Optional[str] = None):
        self.redis = RedisClient(redis_url)
        self.session_id = str(uuid.uuid4())
        self.store = Chroma(
            collection_name="conversation_memory",
            embedding_function=embedding_model,
            persist_directory=persist_dir,
        )
        self.short_term: list[dict] = []
        self.mid_term: str = ""
        self.MAX_SHORT_TERM = 6

    def add(self, role: str, content: str):
        """添加对话到短期记忆（同步写入 Redis + 内存）"""
        entry = {"role": role, "content": content, "timestamp": datetime.now().isoformat()}
        self.short_term.append(entry)
        self.redis.add_short_term(self.session_id, role, content)

    def _score_to_threshold(self, distance: float) -> float:
        """ChromaDB 距离 → 相似度分数"""
        return max(0.0, 1.0 - distance / 2.0)

    def retrieve(self, query: str, k: int = 3, min_score: Optional[float] = None) -> list[str]:
        """从长期记忆检索，支持距离阈值过滤"""
        if min_score is None:
            min_score = float(os.getenv("MEMORY_RETRIEVAL_THRESHOLD", "0.25"))
        try:
            results = self.store.similarity_search_with_score(query, k=k * 3)
            filtered = []
            for doc, score in results:
                similarity = self._score_to_threshold(score)
                if similarity >= min_score:
                    filtered.append((doc, similarity))
            filtered.sort(key=lambda x: x[1], reverse=True)
            return [doc.page_content for doc, _ in filtered[:k]]
        except Exception as e:
            logger.warning("Memory retrieve failed: {}", e)
            return []

    def consolidate(self, llm_func: Callable[[str], str]) -> Optional[str]:
        """同步整理记忆：短期→中期→长期（可在后台线程调用）"""
        if len(self.short_term) <= self.MAX_SHORT_TERM:
            return None

        old = self.short_term[:-self.MAX_SHORT_TERM]
        history = "\n".join([f"{m['role']}: {m['content'][:200]}" for m in old])
        prompt = f"Extract key info from this conversation:\n{history}\nFormat:\n- Intent\n- Facts\n- References\n- Key Terms"
        summary = llm_func(prompt)
        if not summary:
            return None

        doc_id = str(uuid.uuid4())
        self.store.add_texts(
            texts=[summary],
            metadatas=[{"type": "consolidation", "timestamp": datetime.now().isoformat(), "id": doc_id}],
            ids=[doc_id],
        )
        logger.info("Memory consolidated: {} chars", len(summary))

        self.redis.set_mid_term(self.session_id, summary)
        self.mid_term = summary
        self.short_term = self.short_term[-self.MAX_SHORT_TERM:]
        return summary

    def async_consolidate(self, llm_func: Callable[[str], str]):
        """异步后台整理记忆（不阻塞主流程）"""
        t = threading.Thread(target=self.consolidate, args=(llm_func,), daemon=True)
        t.start()

    def get_context(self, query: str, llm_func: Callable) -> str:
        """构建完整上下文：Redis记忆 + 长期向量 + 短期 + 中期"""
        parts = []

        threshold = float(os.getenv("MEMORY_RETRIEVAL_THRESHOLD", "0.25"))
        memories = self.retrieve(query, min_score=threshold)
        if memories:
            parts.append("[Related Past]\n" + "\n---\n".join(memories))

        redis_mid = self.redis.get_mid_term(self.session_id)
        if redis_mid:
            parts.append("[Summary]\n" + redis_mid)

        if self.mid_term:
            parts.append("[Session Summary]\n" + self.mid_term)

        if self.short_term:
            recent = "\n".join([f"{m['role']}: {m['content'][:200]}" for m in self.short_term[-4:]])
            parts.append("[Recent]\n" + recent)

        self.async_consolidate(llm_func)
        return "\n\n".join(parts)

    def extract_entities(self, user_input: str, answer: str, llm_func: Callable):
        """提取实体画像（异步，不阻塞）"""
        pass

    def clear(self):
        """清除当前会话记忆"""
        self.short_term = []
        self.mid_term = ""
        self.session_id = str(uuid.uuid4())
        self.redis.clear_session(self.session_id)

    def stats(self) -> dict:
        return {
            "short_term_rounds": len(self.short_term) // 2,
            "has_mid_term": bool(self.mid_term),
            "redis_available": self.redis.is_available(),
            "long_term_chunks": self.store._collection.count(),
        }