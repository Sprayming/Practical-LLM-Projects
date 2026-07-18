import json
import uuid
import os
import hashlib
from datetime import datetime
from typing import Callable, Optional, List, Dict
from loguru import logger

from langchain_chroma import Chroma
from app.memory.redis_client import RedisClient
from app.memory.forgetting import ForgettingMechanism
from app.worker.shadow_worker import ShadowWorker, ShadowTask, TaskPriority, get_worker


class MemorySystem:
    """
    三层记忆系统框架

    短期：最近 N 轮原话（Redis List，TTL 2h），回退：内存列表
    中期：近期对话摘要（Redis String，TTL 24h），回退：内存字符串
    长期：向量化知识/实体（ChromaDB，永久，带遗忘衰减）

    [2026-07-19] 改进：
      - clear_session：先清理 Redis 再重置 session_id，避免僵尸数据
      - 检索时异步递增 access_count，实现「访问即激活」的反遗忘
      - 完善实体提取（ShadowWorker 后台异步提取并存入长期记忆）
      - 增量摘要合并：整理时将旧摘要与新对话一并提交 LLM
      - Redis 容灾恢复：启动时从 Redis 恢复短期/中期记忆
    """

    def __init__(
        self,
        embedding_model,
        persist_dir: str = "./memory_db",
        redis_url: Optional[str] = None,
        tenant_id: str = "default",
        max_short_term: int = 6,
        forgetting_threshold: float = 0.15,
    ):
        # ---- 基础配置 ----
        self.tenant_id = tenant_id
        self.session_id = str(uuid.uuid4())
        self.max_short_term = max_short_term

        # ---- 存储引擎初始化 ----
        self.redis = RedisClient(redis_url)
        self.store = Chroma(
            collection_name=f"memory_{self.tenant_id}",
            embedding_function=embedding_model,
            persist_directory=persist_dir,
        )

        # ---- 内存回退方案 ----
        self.short_term: List[Dict] = []
        self.mid_term: str = ""

        # ---- 高级机制 ----
        self.forgetting = ForgettingMechanism(threshold=forgetting_threshold)
        self.worker = get_worker()

        # ---- 启动时从 Redis 恢复 ----
        self._restore_from_redis()

    # ==========================================
    # 1. 同步读写接口（高优先级，低延迟）
    # ==========================================

    def add(self, role: str, content: str):
        """同步写入：记录对话到短期记忆"""
        entry = {"role": role, "content": content, "timestamp": datetime.now().isoformat()}
        self.short_term.append(entry)
        self.redis.add_short_term(self.session_id, role, content)

    def retrieve_long_term(self, query: str, k: int = 3, min_score: float = 0.25) -> List[str]:
        """同步读取：从长期记忆检索，带遗忘过滤 + 异步访问计数"""
        try:
            results = self.store.similarity_search_with_score(query, k=k * 3)
            filtered_docs = []
            activated_ids = []

            for doc, distance in results:
                similarity = max(0.0, 1.0 - distance / 2.0)
                if similarity < min_score:
                    continue

                ts = datetime.fromisoformat(doc.metadata.get("timestamp", datetime.now().isoformat()))
                access = doc.metadata.get("access_count", 0)
                forgetting_score = self.forgetting.score(doc.page_content, ts, access)

                if not self.forgetting.should_forget(forgetting_score):
                    doc.metadata["forgetting_score"] = forgetting_score
                    filtered_docs.append(doc)
                    doc_id = doc.metadata.get("id")
                    if doc_id:
                        activated_ids.append((doc_id, access + 1))

            # 异步递增访问计数（反遗忘），不阻塞检索路径
            if activated_ids:
                self._async_bump_access(activated_ids)

            filtered_docs.sort(key=lambda d: d.metadata.get("forgetting_score", 0), reverse=True)
            return [doc.page_content for doc in filtered_docs[:k]]

        except Exception as e:
            logger.error("Long-term retrieval failed: {}", e)
            return []

    def _async_bump_access(self, id_pairs: List[tuple]):
        """异步提交访问计数更新到 Worker"""
        task = ShadowTask(
            name=f"bump_access_{self.tenant_id}_{self.session_id}",
            fn=lambda: self._do_bump_access(id_pairs),
            priority=TaskPriority.LOW,
            max_retries=0,
        )
        self.worker.submit(task)

    def _do_bump_access(self, id_pairs: List[tuple]):
        """在后台线程执行 ChromaDB 元数据更新"""
        try:
            ids = [p[0] for p in id_pairs]
            current_docs = self.store._collection.get(ids=ids)
            updated_metadatas = []
            for doc_id, new_count in id_pairs:
                meta = current_docs["metadatas"][ids.index(doc_id)] if doc_id in ids else {}
                meta = dict(meta) if meta else {}
                meta["access_count"] = new_count
                updated_metadatas.append(meta)
            self.store._collection.update(ids=ids, metadatas=updated_metadatas)
            logger.debug("Bumped access_count for {} docs", len(id_pairs))
        except Exception as e:
            logger.warning("Failed to bump access_count: {}", e)

    def get_context(self, query: str) -> str:
        """组装当前请求的完整上下文"""
        parts = []

        long_memories = self.retrieve_long_term(query)
        if long_memories:
            parts.append("[Related Past]\n" + "\n---\n".join(long_memories))

        mid = self.redis.get_mid_term(self.session_id) or self.mid_term
        if mid:
            parts.append("[Session Summary]\n" + mid)

        if self.short_term:
            recent = "\n".join([f"{m['role']}: {m['content'][:200]}" for m in self.short_term[-4:]])
            parts.append("[Recent]\n" + recent)

        return "\n\n".join(parts)

    # ==========================================
    # 2. 异步整理接口（中低优先级，后台执行）
    # ==========================================

    def trigger_background_jobs(self, llm_func: Callable[[str], str]):
        """触发所有后台异步任务（在每次对话结束后调用）"""
        self._async_consolidate(llm_func)

    def _async_consolidate(self, llm_func: Callable[[str], str]):
        """异步整理：短期溢出时，提炼为中期和长期"""
        if len(self.short_term) <= self.max_short_term:
            return

        task = ShadowTask(
            name=f"consolidate_{self.tenant_id}_{self.session_id}",
            fn=lambda: self._do_consolidate(llm_func),
            priority=TaskPriority.MEDIUM,
            max_retries=1,
        )
        self.worker.submit(task)

    def _do_consolidate(self, llm_func: Callable[[str], str]):
        """实际整理逻辑：增量合并旧摘要 + 新对话"""
        try:
            old = self.short_term[:-self.max_short_term]
            history = "\n".join([f"{m['role']}: {m['content'][:200]}" for m in old])

            # 获取旧摘要，做增量合并
            old_summary = self.redis.get_mid_term(self.session_id) or self.mid_term or ""
            if old_summary:
                prompt = (
                    f"Old Summary:\n{old_summary}\n\n"
                    f"New Conversation:\n{history}\n\n"
                    "Merge them into a concise summary covering all key intents, facts, and terms."
                )
            else:
                prompt = f"Extract key info from this conversation:\n{history}\nFormat:\n- Intent\n- Facts\n- Key Terms"

            summary = llm_func(prompt)
            if not summary:
                return

            doc_id = str(uuid.uuid4())
            self.store.add_texts(
                texts=[summary],
                metadatas=[{"type": "consolidation", "timestamp": datetime.now().isoformat(), "id": doc_id}],
                ids=[doc_id],
            )

            self.redis.set_mid_term(self.session_id, summary)
            self.mid_term = summary
            self.short_term = self.short_term[-self.max_short_term:]
            logger.info("Memory consolidated for session {} ({} chars)", self.session_id, len(summary))

        except Exception as e:
            logger.error("Consolidation failed: {}", e)

    # ==========================================
    # 3. 实体提取（异步，不阻塞）
    # ==========================================

    def extract_entities(self, user_input: str, answer: str, llm_func: Callable):
        """提取实体画像（异步，不阻塞）"""
        task = ShadowTask(
            name=f"extract_entity_{self.tenant_id}_{self.session_id}",
            fn=lambda: self._do_extract_entity(user_input, answer, llm_func),
            priority=TaskPriority.LOW,
            max_retries=1,
        )
        self.worker.submit(task)

    def _do_extract_entity(self, user_input: str, answer: str, llm_func: Callable):
        """后台线程执行实体提取并存入长期记忆"""
        try:
            prompt = (
                f"Extract key user profile entities from the conversation.\n\n"
                f"User: {user_input[:500]}\n"
                f"Assistant: {answer[:500]}\n\n"
                'Output JSON format: {"entities": [{"key": "preference", "value": "likes spicy food"}]}'
            )
            result = llm_func(prompt)
            if not result:
                return

            data = json.loads(result)
            entities = data.get("entities", [])

            for ent in entities:
                key = ent.get("key", "").strip()
                value = ent.get("value", "").strip()
                if not key or not value:
                    continue

                doc_id = f"entity_{self.tenant_id}_{hashlib.md5(key.encode()).hexdigest()[:12]}"
                self.store.add_texts(
                    texts=[f"{key}: {value}"],
                    metadatas=[{
                        "type": "entity",
                        "timestamp": datetime.now().isoformat(),
                        "id": doc_id,
                        "access_count": 1,
                    }],
                    ids=[doc_id],
                )

            if entities:
                logger.info("Extracted {} entities for tenant {}", len(entities), self.tenant_id)

        except (json.JSONDecodeError, Exception) as e:
            logger.debug("Entity extraction skipped: {}", e)

    # ==========================================
    # 4. 系统管理接口
    # ==========================================

    def _restore_from_redis(self):
        """启动时从 Redis 恢复短期和中期记忆（容灾恢复）"""
        if not self.redis.is_available():
            return

        try:
            mid = self.redis.get_mid_term(self.session_id)
            if mid:
                self.mid_term = mid

            short = self.redis.get_short_term(self.session_id)
            if short:
                self.short_term = short

            if mid or short:
                logger.info("Restored memory from Redis for session {}", self.session_id)
        except Exception as e:
            logger.warning("Redis restore failed: {}", e)

    def clear_session(self):
        """清除当前会话记忆"""
        # 先清理旧 session 的 Redis 数据，再重置 ID
        self.redis.clear_session(self.session_id)
        self.short_term = []
        self.mid_term = ""
        self.session_id = str(uuid.uuid4())

    def stats(self) -> Dict:
        """获取记忆系统状态"""
        return {
            "tenant_id": self.tenant_id,
            "session_id": self.session_id,
            "short_term_count": len(self.short_term),
            "has_mid_term": bool(self.mid_term),
            "long_term_chunks": self.store._collection.count(),
            "redis_available": self.redis.is_available(),
        }