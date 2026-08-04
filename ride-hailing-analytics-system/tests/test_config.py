import pytest
from app.config import Settings

class TestSettings:
    """测试配置类"""
    
    def test_settings_defaults(self):
        """测试默认配置"""
        settings = Settings()
        assert settings.db_host == "127.0.0.1"
        assert settings.db_port == 3306
        assert settings.db_name == "ride_hailing"
        assert settings.debug is True
    
    def test_settings_from_env(self, monkeypatch):
        """测试从环境变量加载配置"""
        monkeypatch.setenv("DB_HOST", "localhost")
        monkeypatch.setenv("DB_PORT", "5432")
        monkeypatch.setenv("LLM_API_KEY", "test-key")
        
        settings = Settings()
        assert settings.db_host == "localhost"
        assert settings.db_port == 5432
        assert settings.llm_api_key == "test-key"
    
    def test_settings_validation(self):
        """测试配置验证"""
        # 测试正常配置
        settings = Settings(llm_api_key="test-key")
        assert settings.llm_api_key == "test-key"
        
        # 测试空密钥（当前允许，生产环境应校验）
        settings = Settings(llm_api_key="")
        assert settings.llm_api_key == ""
        
        # 测试类型验证
        settings = Settings(db_port=5432, llm_temperature=0.5)
        assert settings.db_port == 5432
        assert settings.llm_temperature == 0.5