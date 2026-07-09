import json, uuid
from datetime import datetime
from typing import Callable, Optional
from langchain_community.vectorstores import Chroma
from loguru import logger


class MemorySystem:
    """三层记忆系统

    短期：最近3轮对话原文
    中期：压缩摘要（包含关键事实和法条引用）
    长期：存入 Chroma 向量库的可检索记忆
    """

    def __init__(self, embedding_model, persist_dir: str = "./memory_db"):
        self.store = Chroma(
            collection_name="conversation_memory",
            embedding_function=embedding_model,
            persist_directory=persist_dir,
        )
        self.short_term: list[dict] = []
        self.mid_term: str = ""
        self.MAX_SHORT_TERM = 6

    def add(self, role: str, content: str):
        self.short_term.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
        })

    def consolidate(self, llm_func: Callable[[str], str]) -> Optional[str]:
        """整理记忆：短期 → 中期 → 长期"""
        if len(self.short_term) <= self.MAX_SHORT_TERM:
            return None

        old = self.short_term[:-self.MAX_SHORT_TERM]
        history = "\n".join([f"{m['role']}: {m['content'][:200]}" for m in old])

        prompt = f"""Extract key info from this legal conversation:

{history}

Format:
- Intent: user's main legal question
- Facts: key facts mentioned  
- References: specific articles, clauses, or law names
- Key Terms: important legal terms discussed"""

        summary = llm_func(prompt)
        if not summary:
            return None

        doc_id = str(uuid.uuid4())
        self.store.add_texts(
            texts=[summary],
            metadatas=[{
                "type": "consolidation",
                "timestamp": datetime.now().isoformat(),
                "id": doc_id,
            }],
            ids=[doc_id],
        )
        logger.info("Memory consolidated: {} chars", len(summary))

        if self.mid_term:
            merge = llm_func(
                f"Merge these two summaries into one (keep all facts and references):\n"
                f"OLD: {self.mid_term}\nNEW: {summary}\nResult:"
            )
            if merge:
                self.mid_term = merge
        else:
            self.mid_term = summary

        self.short_term = self.short_term[-self.MAX_SHORT_TERM:]
        return summary

    def retrieve(self, query: str, k: int = 3) -> list[str]:
        results = self.store.similarity_search(query, k=k)
        return [r.page_content for r in results] if results else []

    def get_context(self, query: str, llm_func: Callable) -> str:
        parts = []

        memories = self.retrieve(query)
        if memories:
            parts.append("[Related Past Conversations]\n" + "\n---\n".join(memories))

        self.consolidate(llm_func)

        if self.mid_term:
            parts.append("[Conversation Summary]\n" + self.mid_term)

        if self.short_term:
            recent = "\n".join(
                [f"{m['role']}: {m['content'][:200]}" for m in self.short_term[-4:]]
            )
            parts.append("[Recent]\n" + recent)

        return "\n\n".join(parts)

    def clear(self):
        self.short_term = []
        self.mid_term = ""

    def stats(self) -> dict:
        return {
            "short_term_rounds": len(self.short_term) // 2,
            "has_mid_term": bool(self.mid_term),
            "mid_term_chars": len(self.mid_term),
            "long_term_chunks": self.store._collection.count(),
        }
