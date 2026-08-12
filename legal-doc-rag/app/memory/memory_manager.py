"""
app/memory/memory_manager.py —— 三层记忆系统核心编排(MemorySystem)

【作用与功能】
定义 legal-doc-rag 的「三层记忆」架构并负责统一编排:短期记忆(最近几轮对话，
Redis 列表 + 内存回退)、中期记忆(对话摘要，Redis 字符串 + 内存回退)、长期记忆
(向量化知识/实体，ChromaDB 向量库)。同时整合遗忘机制(访问即激活的反遗忘)、
后台异步整理(ShadowWorker)、实体画像提取与 Redis 容灾恢复，对外提供高优先级
的同步读写接口与中低优先级的异步整理接口。

【主要组成】
- `MemorySystem`:三层记忆系统主类，封装 add / retrieve_long_term / get_context /
  trigger_background_jobs / clear_session / stats 等接口

【适用场景】
- 场景1:每次用户对话时同步调用 add 写入短期记忆、get_context 组装上下文
- 场景2:对话结束后调用 trigger_background_jobs 触发异步摘要与实体提取
- 场景3:需要重置会话时调用 clear_session，需要观测状态时调用 stats

【依赖关系】
- 上游调用方:app 主流程 / API 层
- 下游依赖:redis_client、forgetting、profile_store、langchain_chroma、app.worker.shadow_worker
"""

import json
import uuid
import os
from datetime import datetime
from typing import Callable, Optional, List, Dict
from loguru import logger

from langchain_chroma import Chroma
from app.memory.redis_client import RedisClient
from app.memory.forgetting import ForgettingMechanism
from app.worker.shadow_worker import ShadowWorker, ShadowTask, TaskPriority, get_worker
from app.memory.profile_store import ProfileStore


class MemorySystem:
    """
    三层记忆系统框架
    
    记忆层次:
    1. 短期记忆:最近 N 轮对话(Redis List，TTL 2h)
       - 回退方案:内存列表(Redis 不可用时)
    2. 中期记忆:对话摘要(Redis String，TTL 24h)
       - 回退方案:内存字符串(Redis 不可用时)
    3. 长期记忆:向量化知识/实体(ChromaDB，永久存储)
       - 带遗忘机制，通过评分过滤低价值记忆
    
    [2026-07-19] 主要改进:
    - clear_session:先清理 Redis 再重置 session_id，避免僵尸数据
    - 检索时异步递增 access_count，实现"访问即激活"的反遗忘机制
    - 完善实体提取(ShadowWorker 后台异步提取并存入长期记忆)
    - 增量摘要合并:整理时将旧摘要与新对话一并提交 LLM
    - Redis 容灾恢复:启动时从 Redis 恢复短期/中期记忆
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
        """
        初始化记忆系统。
        
        参数:
            embedding_model: 文本嵌入模型，用于向量化长期记忆。
            persist_dir (str): ChromaDB 持久化存储目录。
            redis_url (Optional[str]): Redis 连接 URL，如果未提供则使用本地 Redis。
            tenant_id (str): 租户 ID，用于多租户数据隔离。
            max_short_term (int): 短期记忆保留的最大轮数，默认为 6。
            forgetting_threshold (float): 遗忘阈值，默认为 0.15。
        """
        # ---- 基础配置 ----
        self.tenant_id = tenant_id
        self.session_id = str(uuid.uuid4())  # 生成新的会话 ID
        self.max_short_term = max_short_term  # 短期记忆最大长度

        # ---- 存储引擎初始化 ----
        self.redis = RedisClient(redis_url)  # Redis 客户端(短期/中期记忆)
        self.store = Chroma(
            collection_name=f"memory_{self.tenant_id}",  # 按租户命名向量集合
            embedding_function=embedding_model,
            persist_directory=persist_dir,
        )

        # ---- 内存回退方案(Redis 不可用时使用)----
        self.short_term: List[Dict] = []  # 短期记忆(内存列表)
        self.mid_term: str = ""  # 中期记忆(内存字符串)

        # ---- 高级机制 ----
        self.forgetting = ForgettingMechanism(threshold=forgetting_threshold)  # 遗忘机制
        self.worker = get_worker()  # 异步任务 Worker
        self.profile = ProfileStore()  # 用户画像存储

        # ---- 启动时从 Redis 恢复记忆 ----
        self._restore_from_redis()

    # ==========================================
    # 1. 同步读写接口(高优先级，低延迟)
    # ==========================================

    def add(self, role: str, content: str):
        """
        同步写入:记录对话到短期记忆。
        
        参数:
            role (str): 发言角色(user/assistant)。
            content (str): 对话内容。
        """
        entry = {"role": role, "content": content, "timestamp": datetime.now().isoformat()}
        self.short_term.append(entry)
        self.redis.add_short_term(self.session_id, role, content)

    def retrieve_long_term(self, query: str, k: int = 3, min_score: float = 0.25) -> List[str]:
        """
        同步读取:从长期记忆检索相关内容。
        
        使用相似度搜索结合遗忘评分进行过滤，并异步更新访问计数。
        
        参数:
            query (str): 检索查询文本。
            k (int): 返回的最大结果数，默认为 3。
            min_score (float): 最小相似度阈值，默认为 0.25。
            
        返回:
            List[str]: 相关的记忆内容列表。
        """
        try:
            # 1. 执行相似度搜索(获取 3 倍数量的候选结果)
            results = self.store.similarity_search_with_score(query, k=k * 3)
            filtered_docs = []
            activated_ids = []

            # 2. 过滤并激活记忆
            for doc, distance in results:
                # 计算相似度分数(0-1)
                similarity = max(0.0, 1.0 - distance / 2.0)
                if similarity < min_score:
                    continue

                # 获取记忆的元数据
                ts = datetime.fromisoformat(doc.metadata.get("timestamp", datetime.now().isoformat()))
                access = doc.metadata.get("access_count", 0)
                
                # 计算遗忘评分
                forgetting_score = self.forgetting.score(doc.page_content, ts, access)

                # 保留未遗忘的记忆
                if not self.forgetting.should_forget(forgetting_score):
                    doc.metadata["forgetting_score"] = forgetting_score
                    filtered_docs.append(doc)
                    doc_id = doc.metadata.get("id")
                    if doc_id:
                        activated_ids.append((doc_id, access + 1))

            # 3. 异步更新访问计数(不阻塞检索路径)
            if activated_ids:
                self._async_bump_access(activated_ids)

            # 4. 按遗忘评分降序排序并返回前 k 个结果
            filtered_docs.sort(key=lambda d: d.metadata.get("forgetting_score", 0), reverse=True)
            return [doc.page_content for doc in filtered_docs[:k]]

        except Exception as e:
            logger.error("Long-term retrieval failed: {}", e)
            return []

    def _async_bump_access(self, id_pairs: List[tuple]):
        """
        异步提交访问计数更新到 Worker。
        
        参数:
            id_pairs (List[tuple]): 待更新的记忆 ID 和新计数的列表。
        """
        task = ShadowTask(
            name=f"bump_access_{self.tenant_id}_{self.session_id}",
            fn=lambda: self._do_bump_access(id_pairs),
            priority=TaskPriority.LOW,
            max_retries=0,
        )
        self.worker.submit(task)

    def _do_bump_access(self, id_pairs: List[tuple]):
        """
        在后台线程执行 ChromaDB 元数据更新。
        
        参数:
            id_pairs (List[tuple]): 记忆 ID 和新计数的列表。
        """
        try:
            # 提取所有 ID
            ids = [p[0] for p in id_pairs]
            # 获取当前文档
            current_docs = self.store._collection.get(ids=ids)
            # 准备更新的元数据
            updated_metadatas = []
            for doc_id, new_count in id_pairs:
                # 获取当前元数据
                meta = current_docs["metadatas"][ids.index(doc_id)] if doc_id in ids else {}
                meta = dict(meta) if meta else {}
                # 更新访问计数
                meta["access_count"] = new_count
                updated_metadatas.append(meta)
            # 批量更新
            self.store._collection.update(ids=ids, metadatas=updated_metadatas)
            logger.debug("Bumped access_count for {} docs", len(id_pairs))
        except Exception as e:
            logger.warning("Failed to bump access_count: {}", e)

    def get_context(self, query: str) -> str:
        """
        组装当前请求的完整上下文。
        
        整合长期记忆、中期记忆和短期记忆，构建完整的对话上下文。
        
        参数:
            query (str): 用户查询文本。
            
        返回:
            str: 组装好的完整上下文。
        """
        parts = []

        # 1. 添加相关长期记忆
        long_memories = self.retrieve_long_term(query)
        if long_memories:
            parts.append("[Related Past]\n" + "\n---\n".join(long_memories))

        # 2. 添加中期记忆(对话摘要)
        mid = self.redis.get_mid_term(self.session_id) or self.mid_term
        if mid:
            parts.append("[Session Summary]\n" + mid)

        # 3. 添加短期记忆(最近对话)
        if self.short_term:
            recent = "\n".join([f"{m['role']}: {m['content'][:200]}" for m in self.short_term[-4:]])
            parts.append("[Recent]\n" + recent)

        return "\n\n".join(parts)

    # ==========================================
    # 2. 异步整理接口(中低优先级，后台执行)
    # ==========================================

    def trigger_background_jobs(self, llm_func: Callable[[str], str]):
        """
        触发所有后台异步任务。
        
        在每次对话结束后调用，执行记忆整理和实体提取等任务。
        
        参数:
            llm_func (Callable[[str], str]): 调用 LLM 的函数。
        """
        self._async_consolidate(llm_func)

    def _async_consolidate(self, llm_func: Callable[[str], str]):
        """
        异步整理:当短期记忆溢出时，提炼为中期和长期记忆。
        
        参数:
            llm_func (Callable[[str], str]): 调用 LLM 的函数。
        """
        # 只有当短期记忆超过最大长度时才执行
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
        """
        实际整理逻辑:增量合并旧摘要 + 新对话。
        
        参数:
            llm_func (Callable[[str], str]): 调用 LLM 的函数。
        """
        try:
            # 1. 准备待整理的历史对话
            old = self.short_term[:-self.max_short_term]
            history = "\n".join([f"{m['role']}: {m['content'][:200]}" for m in old])

            # 2. 获取旧摘要，做增量合并
            old_summary = self.redis.get_mid_term(self.session_id) or self.mid_term or ""
            if old_summary:
                # 如果有旧摘要，进行增量合并
                prompt = (
                    f"Old Summary:\n{old_summary}\n\n"
                    f"New Conversation:\n{history}\n\n"
                    "Merge them into a concise summary covering all key intents, facts, and terms."
                )
            else:
                # 如果没有旧摘要，直接生成新摘要
                prompt = f"Extract key info from this conversation:\n{history}\nFormat:\n- Intent\n- Facts\n- Key Terms"

            # 3. 生成新摘要
            summary = llm_func(prompt)
            if not summary:
                return

            # 4. 存储摘要到长期记忆和 Redis
            doc_id = str(uuid.uuid4())
            self.store.add_texts(
                texts=[summary],
                metadatas=[{"type": "consolidation", "timestamp": datetime.now().isoformat(), "id": doc_id}],
                ids=[doc_id],
            )

            # 5. 更新中期记忆
            self.redis.set_mid_term(self.session_id, summary)
            self.mid_term = summary
            # 6. 保留最近的短期记忆
            self.short_term = self.short_term[-self.max_short_term:]
            logger.info("Memory consolidated for session {} ({} chars)", self.session_id, len(summary))

        except Exception as e:
            logger.error("Consolidation failed: {}", e)

    # ==========================================
    # 3. 实体提取(异步，不阻塞)
    # ==========================================

    def extract_entities(self, user_input: str, answer: str, llm_func: Callable):
        """
        提取实体画像(异步，不阻塞)。
        
        从用户输入和回答中提取实体信息，并存入用户画像存储。
        
        参数:
            user_input (str): 用户输入文本。
            answer (str): AI 回答文本。
            llm_func (Callable): 调用 LLM 的函数。
        """
        task = ShadowTask(
            name=f"extract_entity_{self.tenant_id}_{self.session_id}",
            fn=lambda: self._do_extract_entity(user_input, answer, llm_func),
            priority=TaskPriority.LOW,
            max_retries=1,
        )
        self.worker.submit(task)

    def _do_extract_entity(self, user_input: str, answer: str, llm_func: Callable):
        """
        后台实体提取逻辑。
        
        将提取的实体存入 ProfileStore(不是 ChromaDB)。
        
        参数:
            user_input (str): 用户输入文本。
            answer (str): AI 回答文本。
            llm_func (Callable): 调用 LLM 的函数。
        """
        try:
            # 构建提示词
            prompt = (
                "Extract key user profile entities. " +
                "Output format: entities as JSON list with key, value, confidence. " +
                "User: " + str(user_input[:500]) + "\n" +
                "Assistant: " + str(answer[:500])
            )
            # 调用 LLM 提取实体
            result = llm_func(prompt)
            if not result:
                return
            # 解析结果并存储
            data = json.loads(result)
            entities = data.get("entities", [])
            if entities:
                self.profile.merge_entities(self.tenant_id, entities)
                logger.info("Extracted {} entities for tenant {}", len(entities), self.tenant_id)
        except (json.JSONDecodeError, Exception) as e:
            logger.debug("Entity extraction skipped: {}", e)

    def _restore_from_redis(self):
        """
        从 Redis 恢复短期和中期记忆。
        
        在系统启动时调用，确保 Redis 不可用时不会丢失数据。
        """
        # 检查 Redis 是否可用
        if not hasattr(self, "redis") or not self.redis.is_available():
            return
        try:
            # 恢复中期记忆
            mid = self.redis.get_mid_term(self.session_id)
            if mid:
                self.mid_term = mid
            # 恢复短期记忆
            short = self.redis.get_short_term(self.session_id)
            if short:
                self.short_term = short
        except Exception as e:
            logger.warning("Redis restore failed: {}", e)

    def clear_session(self):
        """
        清除当前会话记忆。
        
        先清理 Redis 中的旧数据，再重置 session_id，避免僵尸数据。
        """
        # 1. 清理 Redis 中的旧数据
        self.redis.clear_session(self.session_id)
        # 2. 清理内存中的数据
        self.short_term = []
        self.mid_term = ""
        # 3. 生成新的 session_id
        self.session_id = str(uuid.uuid4())

    def stats(self) -> Dict:
        """
        获取记忆系统状态。
        
        返回:
            Dict: 包含各项记忆统计信息的字典。
        """
        return {
            "tenant_id": self.tenant_id,
            "session_id": self.session_id,
            "short_term_count": len(self.short_term),
            "has_mid_term": bool(self.mid_term),
            "long_term_chunks": self.store._collection.count(),
            "redis_available": self.redis.is_available(),
        }
