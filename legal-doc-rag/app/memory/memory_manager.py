import json
import uuid
import os
from datetime import datetime
from typing import Callable, Optional, List, Dict
from loguru import logger

# 假设的依赖导入
from langchain_chroma import Chroma
from app.memory.redis_client import RedisClient
from app.memory.forgetting import ForgettingMechanism
from app.worker.shadow_worker import ShadowWorker, ShadowTask, TaskPriority, get_worker


class MemorySystem:
    """
    三层记忆系统框架
    短期：最近 N 轮原话（Redis List，TTL 2h）
    中期：近期对话摘要（Redis String，TTL 24h）
    长期：向量化知识/实体（ChromaDB，永久，带遗忘衰减）
    """

    def __init__(
        self, 
        embedding_model, 
        persist_dir: str = "./memory_db", 
        redis_url: Optional[str] = None,
        tenant_id: str = "default",
        max_short_term: int = 6,
        forgetting_threshold: float = 0.15
    ):
        # ---- 基础配置 ----
        self.tenant_id = tenant_id
        self.session_id = str(uuid.uuid4())
        self.max_short_term = max_short_term
        
        # ---- 存储引擎初始化 ----
        self.redis = RedisClient(redis_url)
        self.store = Chroma(
            collection_name=f"memory_{self.tenant_id}", # 租户隔离
            embedding_function=embedding_model,
            persist_directory=persist_dir,
        )
        
        # ---- 内存回退方案 ----
        self.short_term: List[Dict] = []
        self.mid_term: str = ""
        
        # ---- 高级机制 ----
        self.forgetting = ForgettingMechanism(threshold=forgetting_threshold)
        self.worker = get_worker()

    # ==========================================
    # 1. 同步读写接口（高优先级，低延迟）
    # ==========================================

    def add(self, role: str, content: str):
        """同步写入：记录对话到短期记忆"""
        entry = {"role": role, "content": content, "timestamp": datetime.now().isoformat()}
        # 1. 写入内存
        self.short_term.append(entry)
        # 2. 同步写入 Redis
        self.redis.add_short_term(self.session_id, role, content)

    def retrieve_long_term(self, query: str, k: int = 3, min_score: float = 0.25) -> List[str]:
        """同步读取：从长期记忆检索相关知识点"""
        try:
            # 多取一些，为遗忘过滤留出余量
            results = self.store.similarity_search_with_score(query, k=k * 3)
            filtered_docs = []
            
            for doc, distance in results:
                # 1. 相似度过滤
                similarity = max(0.0, 1.0 - distance / 2.0)
                if similarity < min_score:
                    continue
                
                # 2. 遗忘机制过滤
                ts = datetime.fromisoformat(doc.metadata.get("timestamp", datetime.now().isoformat()))
                access = doc.metadata.get("access_count", 0)
                forgetting_score = self.forgetting.score(doc.page_content, ts, access)
                
                if not self.forgetting.should_forget(forgetting_score):
                    doc.metadata["forgetting_score"] = forgetting_score
                    filtered_docs.append(doc)
                    
            # 按遗忘分数（清晰度）降序排列
            filtered_docs.sort(key=lambda d: d.metadata.get("forgetting_score", 0), reverse=True)
            return [doc.page_content for doc in filtered_docs[:k]]
            
        except Exception as e:
            logger.error("Long-term retrieval failed: {}", e)
            return []

    def get_context(self, query: str) -> str:
        """组装当前请求的完整上下文"""
        parts = []
        
        # 1. 长期记忆检索
        long_memories = self.retrieve_long_term(query)
        if long_memories:
            parts.append("[Related Past]\n" + "\n---\n".join(long_memories))
            
        # 2. 中期记忆摘要
        mid = self.redis.get_mid_term(self.session_id) or self.mid_term
        if mid:
            parts.append("[Session Summary]\n" + mid)
            
        # 3. 短期记忆原话
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
        # 可以在此处触发实体提取等
        # self._async_extract_entities(llm_func)

    def _async_consolidate(self, llm_func: Callable[[str], str]):
        """异步整理：短期溢出时，提炼为中期和长期"""
        if len(self.short_term) <= self.max_short_term:
            return # 未溢出，不整理

        task = ShadowTask(
            name=f"consolidate_{self.tenant_id}_{self.session_id}",
            fn=lambda: self._do_consolidate(llm_func),
            priority=TaskPriority.MEDIUM,
            max_retries=1
        )
        self.worker.submit(task)

    def _do_consolidate(self, llm_func: Callable[[str], str]):
        """实际整理逻辑（在后台线程执行）"""
        try:
            # 1. 取出溢出的旧对话
            old = self.short_term[:-self.max_short_term]
            history = "\n".join([f"{m['role']}: {m['content'][:200]}" for m in old])
            
            # 2. LLM 生成摘要
            prompt = f"Extract key info from this conversation:\n{history}\nFormat:\n- Intent\n- Facts\n- Key Terms"
            summary = llm_func(prompt)
            if not summary: return

            # 3. 存入长期向量库
            doc_id = str(uuid.uuid4())
            self.store.add_texts(
                texts=[summary],
                metadatas=[{"type": "consolidation", "timestamp": datetime.now().isoformat(), "id": doc_id}],
                ids=[doc_id],
            )

            # 4. 更新中期记忆 & 清理短期记忆
            self.redis.set_mid_term(self.session_id, summary)
            self.mid_term = summary
            self.short_term = self.short_term[-self.max_short_term:]
            logger.info("Memory consolidated successfully for session {}", self.session_id)
            
        except Exception as e:
            logger.error("Consolidation failed: {}", e)

    # ==========================================
    # 3. 实体提取（异步，不阻塞）
    # ==========================================

    def extract_entities(self, user_input: str, answer: str, llm_func: Callable):
        """提取实体画像（异步，不阻塞）"""
        pass  # 预留：未来接入数据库持久化


    # ==========================================
    # 3. 系统管理接口
    # ==========================================

    def clear_session(self):
        """清除当前会话记忆"""
        self.short_term = []
        self.mid_term = ""
        self.session_id = str(uuid.uuid4()) # 重置会话ID
        self.redis.clear_session(self.session_id)

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
