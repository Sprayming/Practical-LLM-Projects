"""
Unit tests for app.api.chat module.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from fastapi.testclient import TestClient


class TestChatAPI:
    """Tests for Chat API endpoints."""

    @patch("app.api.chat.get_user_from_token")
    @patch("app.api.chat.create_embedder")
    @patch("app.api.chat.Chroma")
    @patch("app.api.chat.QueryRewriter")
    @patch("app.api.chat.QueryCache")
    @patch("app.api.chat.CitationTracker")
    @patch("app.api.chat.HybridRetriever")
    @patch("app.api.chat.MemorySystem")
    def test_chat_endpoint_no_vector_store(
        self, mock_memory, mock_retriever, mock_citation, 
        mock_cache, mock_rewriter, mock_chroma, mock_embedder, mock_auth
    ):
        """Test chat endpoint when no vector store exists."""
        from app.main import app
        
        # Mock authentication
        mock_auth.return_value = {"user_id": "test-user", "tenant_id": "test-tenant"}
        
        # Mock embedder and vector store
        mock_embedder_instance = Mock()
        mock_embedder.return_value = mock_embedder_instance
        
        # Mock _build_pipeline to return None vector store
        with patch("app.api.chat._build_pipeline") as mock_pipeline:
            mock_pipeline.return_value = (None, None, None, None, None)
            
            client = TestClient(app)
            response = client.post(
                "/api/chat",
                json={"message": "Test message"},
                headers={"Authorization": "Bearer test-token"}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert "answer" in data
            assert data["answer"] == "请先上传文档"

    @patch("app.api.chat.get_user_from_token")
    @patch("app.api.chat.create_embedder")
    @patch("app.api.chat.Chroma")
    @patch("app.api.chat.QueryRewriter")
    @patch("app.api.chat.QueryCache")
    @patch("app.api.chat.CitationTracker")
    @patch("app.api.chat.HybridRetriever")
    @patch("app.api.chat.MemorySystem")
    def test_chat_endpoint_with_cache_hit(
        self, mock_memory, mock_retriever, mock_citation, 
        mock_cache, mock_rewriter, mock_chroma, mock_embedder, mock_auth
    ):
        """Test chat endpoint with cache hit."""
        from app.main import app
        
        # Mock authentication
        mock_auth.return_value = {"user_id": "test-user", "tenant_id": "test-tenant"}
        
        # Mock pipeline components
        mock_embedder_instance = Mock()
        mock_embedder.return_value = mock_embedder_instance
        
        mock_vector_store = Mock()
        mock_rewriter_instance = Mock()
        mock_rewriter_instance.rewrite.return_value = ["Test query"]
        mock_rewriter.return_value = mock_rewriter_instance
        
        mock_cache_instance = Mock()
        mock_cache_instance.get.return_value = "Cached response"
        mock_cache.return_value = mock_cache_instance
        
        mock_citation_instance = Mock()
        mock_citation.return_value = mock_citation_instance
        
        with patch("app.api.chat._build_pipeline") as mock_pipeline:
            mock_pipeline.return_value = (
                mock_embedder_instance, mock_vector_store, 
                mock_rewriter_instance, mock_cache_instance, mock_citation_instance
            )
            
            client = TestClient(app)
            response = client.post(
                "/api/chat",
                json={"message": "Test message", "stream": False},
                headers={"Authorization": "Bearer test-token"}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert "answer" in data
            assert data["answer"] == "Cached response"

    @patch("app.api.chat.get_user_from_token")
    def test_chat_endpoint_unauthorized(self, mock_auth):
        """Test chat endpoint without authorization."""
        from app.main import app
        
        mock_auth.side_effect = Exception("Unauthorized")
        
        client = TestClient(app)
        response = client.post(
            "/api/chat",
            json={"message": "Test message"}
        )
        
        assert response.status_code == 422  # Missing authorization header

    @patch("app.api.chat.get_user_from_token")
    def test_chat_endpoint_invalid_token(self, mock_auth):
        """Test chat endpoint with invalid token."""
        from app.main import app
        
        mock_auth.side_effect = Exception("Invalid token")
        
        client = TestClient(app)
        response = client.post(
            "/api/chat",
            json={"message": "Test message"},
            headers={"Authorization": "Bearer invalid-token"}
        )
        
        assert response.status_code == 500  # Server error due to invalid token