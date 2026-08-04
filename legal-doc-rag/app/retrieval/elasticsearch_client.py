"""
Elasticsearch Client for Legal-DOC-RAG.

Provides:
- Elasticsearch connection management
- Index creation and management
- Document indexing and search
- Chinese text analysis (using IK analyzer)
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
        Initialize Elasticsearch client.

        Args:
            hosts: List of Elasticsearch hosts (default: from env or localhost:9200)
            index_name: Name of the index
            timeout: Connection timeout in seconds
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
        """Check if Elasticsearch is available."""
        return self.client is not None

    def create_index(self, recreate: bool = False) -> bool:
        """
        Create the search index with Chinese analyzer.

        Args:
            recreate: If True, delete and recreate the index

        Returns:
            True if successful
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
        Index a document.

        Args:
            doc_id: Document ID
            content: Document content
            source: Source filename
            tenant_id: Tenant ID
            chunk_index: Chunk index
            metadata: Additional metadata

        Returns:
            True if successful
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
        Search documents using full-text search.

        Args:
            query: Search query
            tenant_id: Tenant ID to filter by
            size: Number of results to return
            min_score: Minimum score threshold

        Returns:
            List of search results
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
        Delete all documents from a source.

        Args:
            source: Source filename
            tenant_id: Tenant ID

        Returns:
            Number of deleted documents
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
        Get document count.

        Args:
            tenant_id: Optional tenant ID to filter by

        Returns:
            Number of documents
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
        Check Elasticsearch health.

        Returns:
            Health status dictionary
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
    """Get or create Elasticsearch client singleton."""
    global _es_client
    if _es_client is None:
        try:
            _es_client = ElasticsearchClient()
            if _es_client.is_available():
                _es_client.create_index()
        except Exception as e:
            logger.warning("Failed to initialize Elasticsearch: {}", e)
    return _es_client