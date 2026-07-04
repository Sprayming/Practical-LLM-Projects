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

import chromadb
from chromadb.config import Settings as ChromaSettings
from loguru import logger

from app.config import settings, CHROMA_COLLECTION_NAME
from app.models import DocumentMeta


class VectorStore:
    """ChromaDB 封装类。管理向量库的读写操作。"""

    def __init__(self, persist_dir: Optional[str] = None) -> None:
        # 持久化目录：数据库文件存放在这里，重启不丢失
        self._persist_dir = Path(persist_dir or settings.CHROMA_PERSIST_DIR)
        self._persist_dir.mkdir(parents=True, exist_ok=True )#如果不存在则创建

        self._client = chromadb.PersistentClient(
            path = str(self._persist_dir),
            settings=ChromaSettings(anonymized_telemetry=False),#匿名化遥测
        )
        self._collection = self._client.get_or_create_collection(
            name=CHROMA_COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(f"VectorStore 初始化完成，持久化目录：{self._persist_dir}")
        

    def add_embeddings(
        self,
        ids: list[str],                  # 每个块的唯一 ID
        embeddings: list[list[float]],   # 向量数组
        documents: list[str],            # 原文文本
        metadatas: list[dict],           # 元信息（文件名、页码等）

    ) -> None:
        """添加向量到数据库。"""
        self._collection.add(
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
            ids=ids,
        )


    def search(
        self,
        query_embedding: list[float],   # 查询的向量
        top_k: int = 10,                # 返回多少条结果
        where: Optional[dict] = None,   # 过滤条件（可选）
    ) -> list[tuple[str, float, str, dict]]:
        """搜索最相似的向量。"""
        results = self._collection.query(
            query_embeddings=[query_embedding],
            where=where,
            include=["documents", "metadatas", "ids", "distances"],
            top_k=top_k,
        )
        
        items:list[tuple[str, float, str, dict]] = []
        if not results["ids"]:
            return items #空列表
        
        # 将结果转换为元组列表
        for i in range(len(results["ids"][0])):

            score=1.0-(results["distances"][0][i]if results["distances"] else 0.0) #距离越小，相似度越高
            items.append(
                (
                    results["ids"][0][i], #唯一ID
                    score,               #相似度
                    results["documents"][0][i], #原文文本
                    results["metadatas"][0][i], #元信息
                )
            )

        return items
    

    def delete_by_document_id(self, document_id: str) -> bool:
        """根据文档 ID 删除向量。"""
        try:
            results= self._collection.get(
                where={"document_id": document_id})
            if results["ids"]:

                self._collection.delete(ids=results["ids"])
                logger.info(f"删除向量成功，document_id: {document_id}")
            return True
        except Exception as e:
            logger.error(f"删除向量失败，document_id: {document_id}, 错误信息: {e}")
            return False
        

    def list_documents(self) -> list[DocumentMeta]:
        """列出所有文档的元信息。"""
        data= self._collection.get(include=["metadatas", "ids", "documents"])
        if not data["ids"]:
                return []
        

        #将结果依据document_id去重分组统计
        doc_map:dict[str, DocumentMeta] = {}
        for i in range(len(data["ids"])):
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
    


    # 单例模式
    @property
    def count(self) -> int:
        """返回数据库中的向量数量。"""
        # return len(self._collection.get(include=["metadatas", "ids", "documents"])["ids"])
        return self._collection.count()#返回数据库中的向量数量

    def health(self) -> dict:
        """检查数据库是否健康。"""
        return  {
            "collection": CHROMA_COLLECTION_NAME,
            "chunk_count": self.count,
            "document_count": len(self.list_documents()),
        }


#单例
_store: Optional[VectorStore] = None
def get_vector_store() -> VectorStore:
    global _store
    if _store is None:
        _store = VectorStore()
    return _store