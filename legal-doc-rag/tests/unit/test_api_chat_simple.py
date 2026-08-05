"""
Simple unit tests for app.api.chat module.
"""
import pytest
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient


class TestChatAPI:
    """Tests for Chat API endpoints."""

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
        
        # Should return 422 due to missing authorization header
        assert response.status_code == 422

    def test_chat_endpoint_invalid_token(self):
        """非法 token -> 401（真 JWT 校验，不再进入业务逻辑）。"""
        from app.main import app

        client = TestClient(app)
        response = client.post(
            "/api/chat",
            json={"message": "Test message"},
            headers={"Authorization": "Bearer invalid-token"}
        )
        assert response.status_code == 401

    def test_chat_endpoint_missing_message(self):
        """缺 message 字段（带合法 token）-> 422 请求体校验。"""
        from app.main import app
        from app.api.auth import _create_token

        token = _create_token({"username": "u", "tenant_id": "t", "role": "user"})
        client = TestClient(app)
        response = client.post(
            "/api/chat",
            json={},
            headers={"Authorization": f"Bearer {token}"}
        )
        # 鉴权通过后才做请求体校验，缺必填字段 -> 422
        assert response.status_code == 422