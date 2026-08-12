"""
test_config.py —— 对 app.core.config 配置模块的单元测试。

【测试覆盖范围】
- 基础路径：验证 BASE_DIR 为 Path 对象且目录真实存在、并能正确指向项目根目录。
- 配置默认值：验证 LLM / 嵌入模型 / 存储 / Redis / JWT / 租户库 等各类配置的
  默认值类型与取值（如 REDIS_URL 含 redis://、TENANT_DB 以 users.db 结尾）。
- 环境变量覆盖：验证通过环境变量（如 LLM_API_KEY）可覆盖默认配置值（reload 后生效）。

【适用场景】
- 用 pytest 运行，验证配置模块在「默认值」与「环境变量覆盖」两种场景下的正确性。

【依赖】
- 依赖 app.core.config，使用 os.environ + importlib.reload 模拟环境变量覆盖。
"""
import os
import pytest
from pathlib import Path
from unittest.mock import patch


class TestConfig:
    """配置模块的测试类"""

    def test_base_dir_is_path(self):
        """
        测试 BASE_DIR 是 Path 对象
        
        验证：
        1. BASE_DIR 类型正确
        """
        from app.core.config import BASE_DIR
        assert isinstance(BASE_DIR, Path)

    def test_base_dir_exists(self):
        """
        测试 BASE_DIR 目录存在
        
        验证：
        1. BASE_DIR 指向的目录确实存在
        """
        from app.core.config import BASE_DIR
        assert BASE_DIR.exists()

    def test_llm_config_defaults(self):
        """
        测试 LLM 配置默认值
        
        验证：
        1. LLM_BASE_URL 有默认值
        2. LLM_MODEL 有默认值
        """
        from app.core.config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL
        # 这些应该有默认值或从环境变量读取
        assert isinstance(LLM_BASE_URL, str)
        assert isinstance(LLM_MODEL, str)

    def test_embedding_config_defaults(self):
        """
        测试嵌入模型配置默认值
        
        验证：
        1. EMBEDDER_TYPE 有默认值
        2. EMBEDDING_BASE_URL 有默认值
        3. EMBEDDING_MODEL 有默认值
        """
        from app.core.config import EMBEDDER_TYPE, EMBEDDING_BASE_URL, EMBEDDING_MODEL
        assert isinstance(EMBEDDER_TYPE, str)
        assert isinstance(EMBEDDING_BASE_URL, str)
        assert isinstance(EMBEDDING_MODEL, str)

    def test_storage_config_defaults(self):
        """
        测试存储配置默认值
        
        验证：
        1. CHROMA_PERSIST_DIR 有默认值
        2. UPLOAD_DIR 有默认值
        """
        from app.core.config import CHROMA_PERSIST_DIR, UPLOAD_DIR
        assert isinstance(CHROMA_PERSIST_DIR, str)
        assert isinstance(UPLOAD_DIR, str)

    def test_redis_config_default(self):
        """
        测试 Redis 配置默认值
        
        验证：
        1. REDIS_URL 有默认值
        2. 默认值包含 redis:// 协议
        """
        from app.core.config import REDIS_URL
        assert isinstance(REDIS_URL, str)
        assert "redis://" in REDIS_URL

    def test_jwt_secret_default(self):
        """
        测试 JWT 密钥配置
        
        验证：
        1. JWT_SECRET 是字符串
        2. JWT_SECRET 不为空
        """
        from app.core.config import JWT_SECRET
        assert isinstance(JWT_SECRET, str)
        assert len(JWT_SECRET) > 0

    def test_tenant_db_path(self):
        """
        测试租户数据库路径
        
        验证：
        1. TENANT_DB 是字符串
        2. 路径以 users.db 结尾
        """
        from app.core.config import TENANT_DB
        assert isinstance(TENANT_DB, str)
        assert TENANT_DB.endswith("users.db")

    def test_env_override(self):
        """
        测试环境变量覆盖默认值
        
        验证：
        1. 环境变量可以覆盖配置值
        2. 重新导入模块后能获取到新值
        """
        with patch.dict(os.environ, {"LLM_API_KEY": "test-key"}):
            # 重新导入以获取新值（环境变量需在模块加载时读取）
            import importlib
            import app.core.config
            importlib.reload(app.core.config)
            assert app.core.config.LLM_API_KEY == "test-key"

    def test_base_dir_parent(self):
        """
        测试 BASE_DIR 的正确计算
        
        验证：
        1. BASE_DIR 指向正确的项目根目录
        """
        from app.core.config import BASE_DIR
        # BASE_DIR 应该指向项目根目录（legal-doc-rag/）
        assert BASE_DIR.name == "legal-doc-rag" or BASE_DIR.name == "app"  # 根据项目结构可能不同
