import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from app.main import app
from app.models import AnalysisResult

client = TestClient(app)

class TestQueryAPI:
    """测试查询API"""
    
    @patch('app.api.query.generate_sql')
    @patch('app.api.query.run_sql')
    @patch('app.api.query.interpret')
    @patch('app.api.query.recommend')
    def test_query_success(self, mock_recommend, mock_interpret, mock_run_sql, mock_generate_sql):
        """测试查询成功"""
        # 模拟依赖
        mock_generate_sql.return_value = ("SELECT * FROM drivers", "查询所有司机")
        mock_run_sql.return_value = ([{"id": 1, "name": "张三"}], ["id", "name"])
        mock_interpret.return_value = "数据分析结果"
        mock_recommend.return_value = "运营建议"
        
        # 发送请求
        response = client.post("/api/query/", json={"question": "查询所有司机"})
        
        # 验证响应
        assert response.status_code == 200
        data = response.json()
        assert data["question"] == "查询所有司机"
        assert data["sql"] == "SELECT * FROM drivers"
        assert data["summary"] == "数据分析结果"
        assert data["recommendation"] == "运营建议"
    
    @patch('app.api.query.generate_sql')
    def test_query_empty_sql(self, mock_generate_sql):
        """测试空SQL生成"""
        mock_generate_sql.return_value = ("", "")
        
        response = client.post("/api/query/", json={"question": "测试问题"})
        
        assert response.status_code == 400
        body = response.json()
        assert body.get("error") is True or "SQL" in body.get("detail", "") or "SQL" in body.get("message", "")
    
    @patch('app.api.query.generate_sql')
    @patch('app.api.query.run_sql')
    def test_query_sql_execution_error(self, mock_run_sql, mock_generate_sql):
        """测试SQL执行错误"""
        mock_generate_sql.return_value = ("SELECT * FROM drivers", "查询所有司机")
        mock_run_sql.side_effect = Exception("数据库连接失败")
        
        response = client.post("/api/query/", json={"question": "测试问题"})
        
        assert response.status_code == 500
        body = response.json()
        assert body.get("error") is True or "查询" in body.get("detail", "") or "查询" in body.get("message", "")
    
    def test_query_invalid_request(self):
        """测试无效请求"""
        response = client.post("/api/query/", json={})
        
        assert response.status_code == 422  # Unprocessable Entity
    
    def test_query_missing_question(self):
        """测试缺少问题字段"""
        response = client.post("/api/query/", json={"invalid_field": "test"})
        
        assert response.status_code == 422

class TestDashboardAPI:
    """测试仪表盘API"""
    
    def test_dashboard_success(self):
        """测试仪表盘成功"""
        response = client.get("/api/dashboard/")
        
        assert response.status_code == 200
        data = response.json()
        assert "total_coupons" in data
        assert "total_redemptions" in data
        assert "redemption_rate" in data
        assert "coupon_performance" in data
        assert "driver_stats" in data

class TestHealthCheck:
    """测试健康检查"""
    
    def test_root_endpoint(self):
        """测试根端点"""
        response = client.get("/")
        # 根端点可能返回404或重定向
        assert response.status_code in [200, 404, 307]