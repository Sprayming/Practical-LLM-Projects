"""
Fixed unit tests for app.memory.memory_manager module.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta


class TestMemorySystem:
    """Tests for MemorySystem class."""

    @patch("app.memory.memory_manager.get_worker")
    @patch("app.memory.memory_manager.ProfileStore")
    @patch("app.memory.memory_manager.ForgettingMechanism")
    @patch("app.memory.memory_manager.RedisClient")
    @patch("app.memory.memory_manager.Chroma")
    def test_init(self, mock_chroma, mock_redis, mock_forgetting, mock_profile, mock_worker):
        """Test MemorySystem initialization."""
        from app.memory.memory_manager import MemorySystem
        
        mock_embedding = Mock()
        mock_worker_instance = Mock()
        mock_worker.return_value = mock_worker_instance
        
        memory = MemorySystem(
            embedding_model=mock_embedding,
            persist_dir="./test_db",
            redis_url="redis://localhost:6379/0",
            tenant_id="test-tenant",
            max_short_term=6,
            forgetting_threshold=0.15
        )
        
        assert memory.tenant_id == "test-tenant"
        assert memory.max_short_term == 6
        mock_chroma.assert_called_once()
        mock_redis.assert_called_once()
        mock_forgetting.assert_called_once_with(threshold=0.15)
        mock_worker.assert_called_once()

    @patch("app.memory.memory_manager.get_worker")
    @patch("app.memory.memory_manager.ProfileStore")
    @patch("app.memory.memory_manager.ForgettingMechanism")
    @patch("app.memory.memory_manager.RedisClient")
    @patch("app.memory.memory_manager.Chroma")
    def test_add(self, mock_chroma, mock_redis, mock_forgetting, mock_profile, mock_worker):
        """Test add method."""
        from app.memory.memory_manager import MemorySystem
        
        mock_embedding = Mock()
        mock_redis_instance = Mock()
        mock_redis.return_value = mock_redis_instance
        # 让 Redis 走「不可用」回退分支，short_term 保持为 []（真实环境下 is_available 为 False 时同理）
        mock_redis_instance.is_available.return_value = False

        memory = MemorySystem(
            embedding_model=mock_embedding,
            persist_dir="./test_db"
        )

        memory.add("user", "Hello world")
        
        assert len(memory.short_term) == 1
        assert memory.short_term[0]["role"] == "user"
        assert memory.short_term[0]["content"] == "Hello world"
        mock_redis_instance.add_short_term.assert_called_once()

    @patch("app.memory.memory_manager.get_worker")
    @patch("app.memory.memory_manager.ProfileStore")
    @patch("app.memory.memory_manager.ForgettingMechanism")
    @patch("app.memory.memory_manager.RedisClient")
    @patch("app.memory.memory_manager.Chroma")
    def test_get_context(self, mock_chroma, mock_redis, mock_forgetting, mock_profile, mock_worker):
        """Test get_context method."""
        from app.memory.memory_manager import MemorySystem
        
        mock_embedding = Mock()
        mock_redis_instance = Mock()
        mock_redis.return_value = mock_redis_instance
        mock_redis_instance.get_mid_term.return_value = "Test summary"
        
        memory = MemorySystem(
            embedding_model=mock_embedding,
            persist_dir="./test_db"
        )
        
        # Add some short term memory
        memory.short_term = [
            {"role": "user", "content": "Hello", "timestamp": datetime.now().isoformat()},
            {"role": "assistant", "content": "Hi there", "timestamp": datetime.now().isoformat()}
        ]
        
        # Mock long term retrieval
        memory.retrieve_long_term = Mock(return_value=["Past memory 1", "Past memory 2"])
        
        context = memory.get_context("test query")
        
        assert "[Related Past]" in context
        assert "[Session Summary]" in context
        assert "[Recent]" in context
        assert "Hello" in context

    @patch("app.memory.memory_manager.get_worker")
    @patch("app.memory.memory_manager.ProfileStore")
    @patch("app.memory.memory_manager.ForgettingMechanism")
    @patch("app.memory.memory_manager.RedisClient")
    @patch("app.memory.memory_manager.Chroma")
    def test_clear_session(self, mock_chroma, mock_redis, mock_forgetting, mock_profile, mock_worker):
        """Test clear_session method."""
        from app.memory.memory_manager import MemorySystem
        
        mock_embedding = Mock()
        mock_redis_instance = Mock()
        mock_redis.return_value = mock_redis_instance
        
        memory = MemorySystem(
            embedding_model=mock_embedding,
            persist_dir="./test_db"
        )
        
        old_session_id = memory.session_id
        memory.short_term = [{"role": "user", "content": "test"}]
        memory.mid_term = "test summary"
        
        memory.clear_session()
        
        mock_redis_instance.clear_session.assert_called_once_with(old_session_id)
        assert memory.short_term == []
        assert memory.mid_term == ""
        assert memory.session_id != old_session_id

    @patch("app.memory.memory_manager.get_worker")
    @patch("app.memory.memory_manager.ProfileStore")
    @patch("app.memory.memory_manager.ForgettingMechanism")
    @patch("app.memory.memory_manager.RedisClient")
    @patch("app.memory.memory_manager.Chroma")
    def test_stats(self, mock_chroma, mock_redis, mock_forgetting, mock_profile, mock_worker):
        """Test stats method."""
        from app.memory.memory_manager import MemorySystem
        
        mock_embedding = Mock()
        mock_redis_instance = Mock()
        mock_redis.return_value = mock_redis_instance
        mock_redis_instance.is_available.return_value = True
        
        mock_chroma_instance = Mock()
        mock_chroma.return_value = mock_chroma_instance
        mock_chroma_instance._collection.count.return_value = 10
        
        memory = MemorySystem(
            embedding_model=mock_embedding,
            persist_dir="./test_db",
            tenant_id="test-tenant"
        )
        
        memory.short_term = [{"role": "user", "content": "test"}]
        memory.mid_term = "test summary"
        
        stats = memory.stats()
        
        assert stats["tenant_id"] == "test-tenant"
        assert stats["short_term_count"] == 1
        assert stats["has_mid_term"] is True
        assert stats["long_term_chunks"] == 10
        assert stats["redis_available"] is True

    @patch("app.memory.memory_manager.get_worker")
    @patch("app.memory.memory_manager.ProfileStore")
    @patch("app.memory.memory_manager.ForgettingMechanism")
    @patch("app.memory.memory_manager.RedisClient")
    @patch("app.memory.memory_manager.Chroma")
    def test_retrieve_long_term(self, mock_chroma, mock_redis, mock_forgetting, mock_profile, mock_worker):
        """Test retrieve_long_term method."""
        from app.memory.memory_manager import MemorySystem
        from langchain_core.documents import Document
        
        mock_embedding = Mock()
        mock_redis_instance = Mock()
        mock_redis.return_value = mock_redis_instance
        
        mock_chroma_instance = Mock()
        mock_chroma.return_value = mock_chroma_instance
        
        # Mock similarity search results
        mock_doc = Document(
            page_content="Test content",
            metadata={
                "timestamp": datetime.now().isoformat(),
                "access_count": 0,
                "id": "doc1"
            }
        )
        mock_chroma_instance.similarity_search_with_score.return_value = [
            (mock_doc, 0.1)  # distance
        ]
        
        # Mock forgetting mechanism
        mock_forgetting_instance = Mock()
        mock_forgetting.return_value = mock_forgetting_instance
        mock_forgetting_instance.score.return_value = 0.8
        mock_forgetting_instance.should_forget.return_value = False
        
        memory = MemorySystem(
            embedding_model=mock_embedding,
            persist_dir="./test_db"
        )
        
        results = memory.retrieve_long_term("test query", k=1, min_score=0.25)
        
        assert len(results) == 1
        assert results[0] == "Test content"
        mock_chroma_instance.similarity_search_with_score.assert_called_once()

    @patch("app.memory.memory_manager.get_worker")
    @patch("app.memory.memory_manager.ProfileStore")
    @patch("app.memory.memory_manager.ForgettingMechanism")
    @patch("app.memory.memory_manager.RedisClient")
    @patch("app.memory.memory_manager.Chroma")
    def test_trigger_background_jobs(self, mock_chroma, mock_redis, mock_forgetting, mock_profile, mock_worker):
        """Test trigger_background_jobs method."""
        from app.memory.memory_manager import MemorySystem
        
        mock_embedding = Mock()
        mock_redis_instance = Mock()
        mock_redis.return_value = mock_redis_instance
        mock_redis_instance.is_available.return_value = False

        mock_worker_instance = Mock()
        mock_worker.return_value = mock_worker_instance

        memory = MemorySystem(
            embedding_model=mock_embedding,
            persist_dir="./test_db"
        )

        # 制造短期记忆溢出（超过 max_short_term），触发异步整理任务
        memory.short_term = [
            {"role": "user", "content": f"msg-{i}"}
            for i in range(memory.max_short_term + 1)
        ]

        llm_func = Mock(return_value="Summary")
        memory.trigger_background_jobs(llm_func)

        # 溢出时应向后台 Worker 提交整理任务
        mock_worker_instance.submit.assert_called()