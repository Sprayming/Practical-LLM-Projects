"""
ElasticsearchClient —— legal-doc-rag 的 Elasticsearch 全文检索客户端。

【作用与功能】
封装与 Elasticsearch 的连接管理、索引(中文 IK 分词)创建、文档入库与
全文检索能力，作为混合检索中「全文召回」通道的后端之一。

【主要组成】
- `ElasticsearchClient`:连接管理 + 中文分词索引 + 文档检索/删除/计数/健康检查
- `get_elasticsearch_client`:全局单例获取函数，初始化时自动建索引

【适用场景】
- 场景1:文档入库时为每个 chunk 写入 ES 供全文召回
- 场景2:HybridRetriever 调用 `search` 做全文召回并参与 RRF 融合

【依赖关系】
- 上游调用方:HybridRetriever、索引构建脚本
- 下游依赖:elasticsearch 官方客户端、IK 分词插件、loguru
(原英文说明:连接管理、索引管理、文档索引/搜索、中文 IK 分析)
"""
import os
from typing import List, Dict, Optional, Tuple
from loguru import logger

try:
    from elasticsearch import Elasticsearch
    ELASTICSEARCH_AVAILABLE = True
except ImportError:
    ELASTICSEARCH_AVAILABLE = False
    logger.warning("Elasticsearch client not installed. Install with: pip install elasticsearch")


class ElasticsearchClient:
    """
    Elasticsearch client for full-text search.

    Features:
    - Connection management
    - Index creation with Chinese analyzer
    - Document indexing
    - Full-text search with Chinese support
    """

    def __init__(
        self,
        hosts: List[str] = None,
        index_name: str = "legal-documents",
        timeout: int = 30,
    ):
        """
        初始化 Elasticsearch 客户端。

        当 elasticsearch 库未安装时直接抛 ImportError。否则读取环境变量
        ELASTICSEARCH_HOSTS(逗号分隔)，建立客户端并 ping 探活；
        探活失败仅记录警告、client 置空(后续 is_available 返回 False 降级)。

        参数:
            hosts: ES 主机列表；缺省从 ELASTICSEARCH_HOSTS 或 localhost:9200 读取
            index_name: 索引名(默认 "legal-documents")
            timeout: 连接超时(秒，默认 30)
        异常:
            ImportError: 当 elasticsearch 库未安装时抛出
        """
        if not ELASTICSEARCH_AVAILABLE:
            raise ImportError("Elasticsearch client not installed")

        self.index_name = index_name
        self.client = None

        # Get hosts from environment or default
        if hosts is None:
            hosts_str = os.getenv("ELASTICSEARCH_HOSTS", "http://localhost:9200")
            hosts = [h.strip() for h in hosts_str.split(",")]

        try:
            self.client = Elasticsearch(
                hosts=hosts,
                request_timeout=timeout,
            )
            # Test connection
            if self.client.ping():
                logger.info("Elasticsearch connected: {}", hosts)
            else:
                logger.warning("Elasticsearch connection failed: {}", hosts)
                self.client = None
        except Exception as e:
            logger.error("Elasticsearch initialization failed: {}", e)
            self.client = None

    def is_available(self) -> bool:
        """返回 ES 客户端是否可用(探活成功且已建立连接)。"""
        return self.client is not None

    def create_index(self, recreate: bool = False) -> bool:
        """
        创建带中文 IK 分词器的索引。

        若存在且 recreate=True 则先删除重建；不存在时按 settings/mappings 建索引:
        content 用 chinese_analyzer(ik_max_word 分词)与 ik_smart 搜索分词，
        source/tenant_id/chunk_index/metadata 作为过滤与元数据字段。

        参数:
            recreate: 为 True 时删除已存在索引并重建
        返回:
            bool: 建索引(或已存在)成功返回 True，不可用或异常返回 False
        """
        if not self.is_available():
            return False

        try:
            # Delete index if exists and recreate
            if recreate and self.client.indices.exists(index=self.index_name):
                self.client.indices.delete(index=self.index_name)
                logger.info("Deleted existing index: {}", self.index_name)

            # Create index with Chinese analyzer settings
            if not self.client.indices.exists(index=self.index_name):
                settings = {
                    "analysis": {
                        "analyzer": {
                            "chinese_analyzer": {
                                "type": "custom",
                                "tokenizer": "ik_max_word",
                                "filter": ["lowercase", "stop"]
                            }
                        }
                    }
                },
                mappings = {
                    "properties": {
                        "content": {
                            "type": "text",
                            "analyzer": "chinese_analyzer",
                            "search_analyzer": "ik_smart"
                        },
                        "source": {"type": "keyword"},
                        "tenant_id": {"type": "keyword"},
                        "chunk_index": {"type": "integer"},
                        "metadata": {"type": "object", "enabled": True}
                    }
                }

                self.client.indices.create(
                    index=self.index_name,
                    body={
                        "settings": settings,
                        "mappings": mappings
                    }
                )
                logger.info("Created index: {}", self.index_name)

            return True
        except Exception as e:
            logger.error("Failed to create index: {}", e)
            return False

    def index_document(
        self,
        doc_id: str,
        content: str,
        source: str,
        tenant_id: str,
        chunk_index: int = 0,
        metadata: Dict = None,
    ) -> bool:
        """
        将单个文档 chunk 写入 ES 索引。

        参数:
            doc_id: 文档唯一 ID(建议 chunk 级唯一)
            content: 文档正文内容
            source: 来源文件名
            tenant_id: 租户 ID(用于多租户隔离过滤)
            chunk_index: chunk 序号
            metadata: 附加元数据
        返回:
            bool: 写入成功返回 True，不可用或异常返回 False
        """
        if not self.is_available():
            return False

        try:
            doc = {
                "content": content,
                "source": source,
                "tenant_id": tenant_id,
                "chunk_index": chunk_index,
                "metadata": metadata or {},
            }

            self.client.index(
                index=self.index_name,
                id=doc_id,
                body=doc
            )
            return True
        except Exception as e:
            logger.error("Failed to index document: {}", e)
            return False

    def search(
        self,
        query: str,
        tenant_id: str,
        size: int = 10,
        min_score: float = 0.1,
    ) -> List[Dict]:
        """
        全文检索(按租户过滤的 bool 查询)。

        用 match 对 content 做全文匹配，并用 term 过滤 tenant_id；
        结果按 _score 排序，返回归一化前的原始文档信息列表。

        参数:
            query: 检索查询
            tenant_id: 租户 ID 过滤
            size: 返回结果数量(默认 10)
            min_score: 最低相关性阈值(默认 0.1)
        返回:
            List[Dict]: 每项含 id/score/content/source/metadata
        """
        if not self.is_available():
            return []

        try:
            body = {
                "query": {
                    "bool": {
                        "must": [
                            {"match": {"content": query}}
                        ],
                        "filter": [
                            {"term": {"tenant_id": tenant_id}}
                        ]
                    }
                },
                "size": size,
                "min_score": min_score,
            }

            response = self.client.search(
                index=self.index_name,
                body=body
            )

            results = []
            for hit in response["hits"]["hits"]:
                results.append({
                    "id": hit["_id"],
                    "score": hit["_score"],
                    "content": hit["_source"]["content"],
                    "source": hit["_source"]["source"],
                    "metadata": hit["_source"].get("metadata", {}),
                })

            logger.debug("Elasticsearch search: {} results for query '{}'", len(results), query[:50])
            return results
        except Exception as e:
            logger.error("Elasticsearch search failed: {}", e)
            return []

    def delete_documents_by_source(self, source: str, tenant_id: str) -> int:
        """
        删除指定来源(与租户)下的全部文档。

        参数:
            source: 来源文件名
            tenant_id: 租户 ID
        返回:
            int: 实际删除的文档数量
        """
        if not self.is_available():
            return 0

        try:
            body = {
                "query": {
                    "bool": {
                        "must": [
                            {"term": {"source": source}},
                            {"term": {"tenant_id": tenant_id}}
                        ]
                    }
                }
            }

            response = self.client.delete_by_query(
                index=self.index_name,
                body=body
            )

            deleted = response.get("deleted", 0)
            logger.info("Deleted {} documents from Elasticsearch for source: {}", deleted, source)
            return deleted
        except Exception as e:
            logger.error("Failed to delete documents: {}", e)
            return 0

    def get_document_count(self, tenant_id: str = None) -> int:
        """
        获取索引中的文档总数(可按租户过滤)。

        参数:
            tenant_id: 可选租户 ID，用于按租户计数
        返回:
            int: 文档数量
        """
        if not self.is_available():
            return 0

        try:
            body = {}
            if tenant_id:
                body = {"query": {"term": {"tenant_id": tenant_id}}}

            response = self.client.count(
                index=self.index_name,
                body=body
            )

            return response["count"]
        except Exception as e:
            logger.error("Failed to get document count: {}", e)
            return 0

    def health_check(self) -> Dict:
        """
        检查 ES 集群健康状态。

        返回:
            Dict: 含 status/cluster_name/节点数/分片数；不可用时
            返回 {"status": "unavailable", ...}，异常返回 {"status": "error", ...}
        """
        if not self.is_available():
            return {"status": "unavailable", "message": "Elasticsearch client not initialized"}

        try:
            # Check cluster health
            health = self.client.cluster.health()
            return {
                "status": health["status"],
                "cluster_name": health["cluster_name"],
                "number_of_nodes": health["number_of_nodes"],
                "active_primary_shards": health["active_primary_shards"],
                "active_shards": health["active_shards"],
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}


# Global singleton
_es_client: Optional[ElasticsearchClient] = None


def get_elasticsearch_client() -> Optional[ElasticsearchClient]:
    """获取(或懒创建)Elasticsearch 客户端单例；首次创建时自动建索引。"""
    global _es_client
    if _es_client is None:
        try:
            _es_client = ElasticsearchClient()
            if _es_client.is_available():
                _es_client.create_index()
        except Exception as e:
            logger.warning("Failed to initialize Elasticsearch: {}", e)
    return _es_client