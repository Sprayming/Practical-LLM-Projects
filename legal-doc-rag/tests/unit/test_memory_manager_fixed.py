"""
app.memory.memory_manager 模块的单元测试（修复版）
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta


class TestMemorySystem:
    """记忆系统（MemorySystem）类的测试"""

    @patch("app.memory.memory_manager.get_worker")
    @patch("app.memory.memory_manager.ProfileStore")
    @patch("app.memory.memory_manager.ForgettingMechanism")
    @patch("app.memory.memory_manager.RedisClient")
    @patch("app.memory.memory_manager.Chroma")
    def test_init(self, mock_chroma, mock_redis, mock_forgetting, mock_profile, mock_worker):
        """
        测试记忆系统初始化
        
        验证：
        1. 所有组件正确初始化
        2. 参数正确传递
        3. 外部依赖正确注入
        """
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
        
        # 验证初始化结果
        assert memory.tenant_id == "test-tenant"
        assert memory.max_short_term == 6
        # 验证各组件被正确初始化
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
        """
        测试添加记忆功能
        
        验证：
        1. 短期记忆正确添加
        2. Redis 正确调用
        3. 回退机制正常工作
        """
        from app.memory.memory_manager import MemorySystem
        
        mock_embedding = Mock()
        mock_redis_instance = Mock()
        mock_redis.return_value = mock_redis_instance
        # 模拟 Redis 不可用的情况
        mock_redis_instance.is_available.return_value = False

        memory = MemorySystem(
            embedding_model=mock_embedding,
            persist_dir="./test_db"
        )

        # 添加记忆
        memory.add("user", "Hello world")
        
        # 验证短期记忆添加成功
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
        """
        测试获取上下文功能
        
        验证：
        1. 正确组合不同类型的记忆
        2. 格式化输出正确
        3. 各部分内容完整
        """
        from app.memory.memory_manager import MemorySystem
        
        mock_embedding = Mock()
        mock_redis_instance = Mock()
        mock_redis.return_value = mock_redis_instance
        mock_redis_instance.get_mid_term.return_value = "Test summary"
        
        memory = MemorySystem(
            embedding_model=mock_embedding,
            persist_dir="./test_db"
        )
        
        # 添加短期记忆
        memory.short_term = [
            {"role": "user", "content": "Hello", "timestamp": datetime.now().isoformat()},
            {"role": "assistant", "content": "Hi there", "timestamp": datetime.now().isoformat()}
        ]
        
        # 模拟长期记忆检索
        memory.retrieve_long_term = Mock(return_value=["Past memory 1", "Past memory 2"])
        
        # 获取上下文
        context = memory.get_context("test query")
        
        # 验证上下文包含所有必要的部分
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
        """
        测试清除会话功能
        
        验证：
        1. 会话 ID 正确更新
        2. 所有记忆被清除
        3. Redis 正确调用
        """
        from app.memory.memory_manager import MemorySystem
        
        mock_embedding = Mock()
        mock_redis_instance = Mock()
        mock_redis.return_value = mock_redis_instance
        
        memory = MemorySystem(
            embedding_model=mock_embedding,
            persist_dir="./test_db"
        )
        
        old_session_id = memory.session_id
        # 添加一些记忆
        memory.short_term = [{"role": "user", "content": "test"}]
        memory.mid_term = "test summary"
        
        # 清除会话
        memory.clear_session()
        
        # 验证清除操作
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
        """
        测试统计功能
        
        验证：
        1. 统计信息完整
        2. 各项计数正确
        3. 状态信息准确
        """
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
        
        # 添加一些记忆
        memory.short_term = [{"role": "user", "content": "test"}]
        memory.mid_term = "test summary"
        
        # 获取统计信息
        stats = memory.stats()
        
        # 验证统计信息
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
        """
        测试长期记忆检索功能
        
        验证：
        1. 向量检索正确调用
        2. 遗忘机制正确应用
        3. 结果格式正确
        """
        from app.memory.memory_manager import MemorySystem
        from langchain_core.documents import Document
        
        mock_embedding = Mock()
        mock_redis_instance = Mock()
        mock_redis.return_value = mock_redis_instance
        
        mock_chroma_instance = Mock()
        mock_chroma.return_value = mock_chroma_instance
        
        # 模拟相似性搜索结果
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
        
        # 模拟遗忘机制
        mock_forgetting_instance = Mock()
        mock_forgetting.return_value = mock_forgetting_instance
        mock_forgetting_instance.score.return_value = 0.8
        mock_forgetting_instance.should_forget.return_value = False
        
        memory = MemorySystem(
            embedding_model=mock_embedding,
            persist_dir="./test_db"
        )
        
        # 检索长期记忆
        results = memory.retrieve_long_term("test query", k=1, min_score=0.25)
        
        # 验证结果
        assert len(results) == 1
        assert results[0] == "Test content"
        mock_chroma_instance.similarity_search_with_score.assert_called_once()

    @patch("app.memory.memory_manager.get_worker")
    @patch("app.memory.memory_manager.ProfileStore")
    @patch("app.memory.memory_manager.ForgettingMechanism")
    @patch("app.memory.memory_manager.RedisClient")
    @patch("app.memory.memory_manager.Chroma")
    def test_trigger_background_jobs(self, mock_chroma, mock_redis, mock_forgetting, mock_profile, mock_worker):
        """
        测试后台任务触发功能
        
        验证：
        1. 短期记忆溢出时触发任务
        2. Worker 正确调用
        3. 任务参数正确
        """
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

        # 制造短期记忆溢出（超过 max_short_term）
        memory.short_term = [
            {"role": "user", "content": f"msg-{i}"}
            for i in range(memory.max_short_term + 1)
        ]

        # 模拟 LLM 函数
        llm_func = Mock(return_value="Summary")
        # 触发后台任务
        memory.trigger_background_jobs(llm_func)

        # 验证 Worker 被调用
        mock_worker_instance.submit.assert_called()
