# ============================================================
# 向量存储 — ChromaDB 封装
#
# ChromaDB 是一个本地向量数据库
# 它的作用：存向量 + 搜最相似的向量
# 类似"用语义来搜索"，而不是用关键词
#
# 核心操作只有两个：
#   add_embeddings()  → 存进去
#   search()          → 搜出来
# ============================================================

from __future__ import annotations

from pathlib import Path
from typing import Optional

import chromadb                                           # 向量数据库
from chromadb.config import Settings as ChromaSettings    # 数据库配置
from loguru import logger

from app.config import settings, CHROMA_COLLECTION_NAME
from app.models import DocumentMeta


class VectorStore:
    """ChromaDB 封装类。管理向量库的读写操作。"""

    def __init__(self, persist_dir: Optional[str] = None) -> None:
        # 持久化目录：数据库文件存放在这里，重启不丢失
        self._persist_dir = Path(persist_dir or settings.chroma_persist_dir)
        self._persist_dir.mkdir(parents=True, exist_ok=True)  # 目录不存在就创建

        # 创建 ChromaDB 持久化客户端
        self._client = chromadb.PersistentClient(
            path=str(self._persist_dir),
            settings=ChromaSettings(anonymized_telemetry=False),  # 关掉匿名统计
        )
        
        # 获取或创建一个集合（Collection）
        # 集合 ≈ MySQL 里的表，里面存了一堆向量
        self._collection = self._client.get_or_create_collection(
            name=CHROMA_COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},  # 用余弦距离衡量相似度
        )
        logger.info("ChromaDB ready @ {}", self._persist_dir)

    def add_embeddings(
        self,
        ids: list[str],                  # 每个块的唯一 ID
        embeddings: list[list[float]],   # 向量数组
        documents: list[str],            # 原文文本
        metadatas: list[dict],           # 元信息（文件名、页码等）
    ) -> None:
        """批量添加嵌入向量到数据库。"""
        self._collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )

    def search(
        self,
        query_embedding: list[float],   # 查询的向量
        top_k: int = 10,                # 返回多少条结果
        where: Optional[dict] = None,   # 过滤条件（可选）
    ) -> list[tuple[str, float, str, dict]]:
        """向量搜索：找最相似的 top_k 个块。
        
        返回：[(id, 相似度分数, 原文内容, 元信息), ...]
        分数范围 0~1，越接近 1 越相似。
        """
        results = self._collection.query(
            query_embeddings=[query_embedding],  # 查询向量（需要包一层列表）
            n_results=top_k,
            where=where,                         # 过滤，如 {"document_id": {...}}
            include=["documents", "metadatas", "distances"],  # 需要返回这些字段
        )

        items: list[tuple[str, float, str, dict]] = []
        if not results["ids"]:
            return items  # 没结果就返回空列表

        # 组装结果
        # ChromaDB 返回的是"列表的列表"，所以我们取 [0] 这一组
        for i in range(len(results["ids"][0])):
            # 距离 → 相似度分数（余弦距离 = 1 - 余弦相似度）
            score = 1.0 - (results["distances"][0][i] if results["distances"] else 0.0)
            items.append((
                results["ids"][0][i],
                round(float(score), 4),                     # 保留4位小数
                results["documents"][0][i] if results["documents"] else "",
                results["metadatas"][0][i] if results["metadatas"] else {},
            ))
        return items

    def delete_by_document_id(self, document_id: str) -> bool:
        """删除一个文档的所有块。"""
        try:
            # 先查到这个文档的所有块
            results = self._collection.get(where={"document_id": document_id})
            if results["ids"]:
                # 按 ID 删除
                self._collection.delete(ids=results["ids"])
                logger.info("Deleted {} chunks of doc {}", len(results["ids"]), document_id)
            return True
        except Exception as e:
            logger.error("Failed to delete {}: {}", document_id, e)
            return False

    def list_documents(self) -> list[DocumentMeta]:
        """遍历整个集合，汇总每个文档的信息。"""
        data = self._collection.get(include=["metadatas", "documents"])
        if not data["ids"]:
            return []

        # 按 document_id 分组统计
        doc_map: dict[str, dict] = {}
        for i, mid in enumerate(data["ids"]):
            m = data["metadatas"][i] if data["metadatas"] else {}
            did = m.get("document_id", "unknown")
            if did not in doc_map:
                doc_map[did] = {
                    "id": did,
                    "filename": m.get("filename", "unknown"),
                    "file_size": 0,
                    "file_type": Path(m.get("filename", "")).suffix,
                    "page_count": 0,
                    "char_count": 0,
                    "chunk_count": 0,
                    "created_at": "",
                }
            doc_map[did]["chunk_count"] += 1
            doc_map[did]["char_count"] += len(data["documents"][i] or "")
        return [DocumentMeta(**v) for v in doc_map.values()]

    @property
    def count(self) -> int:
        """集合中的总块数。"""
        return self._collection.count()

    def health(self) -> dict:
        """健康检查信息。"""
        return {
            "collection": CHROMA_COLLECTION_NAME,
            "chunk_count": self.count,
            "document_count": len(self.list_documents()),
        }


# ── 单例 ──
_store: Optional[VectorStore] = None


def get_vector_store() -> VectorStore:
    global _store
    if _store is None:
        _store = VectorStore()
    return _store
