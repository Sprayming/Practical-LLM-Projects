"""
Unit tests for app.core.config module.
"""
import os
import pytest
from pathlib import Path
from unittest.mock import patch


class TestConfig:
    """Tests for configuration module."""

    def test_base_dir_is_path(self):
        """Test that BASE_DIR is a Path object."""
        from app.core.config import BASE_DIR
        assert isinstance(BASE_DIR, Path)

    def test_base_dir_exists(self):
        """Test that BASE_DIR directory exists."""
        from app.core.config import BASE_DIR
        assert BASE_DIR.exists()

    def test_llm_config_defaults(self):
        """Test LLM configuration defaults."""
        from app.core.config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL
        # These should have default values or be read from env
        assert isinstance(LLM_BASE_URL, str)
        assert isinstance(LLM_MODEL, str)

    def test_embedding_config_defaults(self):
        """Test embedding configuration defaults."""
        from app.core.config import EMBEDDER_TYPE, EMBEDDING_BASE_URL, EMBEDDING_MODEL
        assert isinstance(EMBEDDER_TYPE, str)
        assert isinstance(EMBEDDING_BASE_URL, str)
        assert isinstance(EMBEDDING_MODEL, str)

    def test_storage_config_defaults(self):
        """Test storage configuration defaults."""
        from app.core.config import CHROMA_PERSIST_DIR, UPLOAD_DIR
        assert isinstance(CHROMA_PERSIST_DIR, str)
        assert isinstance(UPLOAD_DIR, str)

    def test_redis_config_default(self):
        """Test Redis configuration default."""
        from app.core.config import REDIS_URL
        assert isinstance(REDIS_URL, str)
        assert "redis://" in REDIS_URL

    def test_jwt_secret_default(self):
        """Test JWT secret configuration."""
        from app.core.config import JWT_SECRET
        assert isinstance(JWT_SECRET, str)
        assert len(JWT_SECRET) > 0

    def test_tenant_db_path(self):
        """Test tenant database path."""
        from app.core.config import TENANT_DB
        assert isinstance(TENANT_DB, str)
        assert TENANT_DB.endswith("users.db")

    def test_env_override(self):
        """Test that environment variables override defaults."""
        with patch.dict(os.environ, {"LLM_API_KEY": "test-key"}):
            # Reimport to get fresh values
            import importlib
            import app.core.config
            importlib.reload(app.core.config)
            assert app.core.config.LLM_API_KEY == "test-key"

    def test_base_dir_parent(self):
        """Test that BASE_DIR is correctly calculated."""
        from app.core.config import BASE_DIR
        # BASE_DIR should be project root (legal-doc-rag/)
        assert BASE_DIR.name == "legal-doc-rag" or BASE_DIR.name == "app"  # Depending on structure