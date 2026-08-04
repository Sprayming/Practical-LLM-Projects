import pytest
from pydantic import ValidationError
from app.models import QueryRequest, SQLResult, AnalysisResult, DashboardResponse

class TestQueryRequest:
    """测试查询请求模型"""
    
    def test_valid_request(self):
        """测试有效请求"""
        request = QueryRequest(question="测试问题")
        assert request.question == "测试问题"
    
    def test_empty_question(self):
        """测试空问题"""
        with pytest.raises(ValidationError):
            QueryRequest(question="")
    
    def test_long_question(self):
        """测试超长问题"""
        long_question = "x" * 3000  # 超过2048限制
        with pytest.raises(ValidationError):
            QueryRequest(question=long_question)
    
    def test_max_length_question(self):
        """测试最大长度问题"""
        max_question = "x" * 2048
        request = QueryRequest(question=max_question)
        assert len(request.question) == 2048

class TestSQLResult:
    """测试SQL结果模型"""
    
    def test_valid_result(self):
        """测试有效结果"""
        result = SQLResult(
            sql="SELECT * FROM drivers",
            explanation="查询所有司机",
            data=[{"id": 1, "name": "张三"}],
            columns=["id", "name"]
        )
        assert result.sql == "SELECT * FROM drivers"
        assert result.explanation == "查询所有司机"
        assert len(result.data) == 1
    
    def test_empty_result(self):
        """测试空结果"""
        result = SQLResult(
            sql="SELECT * FROM drivers",
            explanation="查询所有司机"
        )
        assert result.data == []
        assert result.columns == []

class TestAnalysisResult:
    """测试分析结果模型"""
    
    def test_valid_analysis(self):
        """测试有效分析结果"""
        result = AnalysisResult(
            question="测试问题",
            sql="SELECT * FROM drivers",
            summary="分析摘要",
            insight="业务洞察",
            recommendation="建议",
            data=[{"id": 1}],
            latency_ms=150.5,
            tokens_used=1000
        )
        assert result.question == "测试问题"
        assert result.latency_ms == 150.5
        assert result.tokens_used == 1000
    
    def test_default_values(self):
        """测试默认值"""
        result = AnalysisResult(
            question="测试问题",
            sql="SELECT * FROM drivers",
            summary="分析摘要",
            insight="业务洞察",
            recommendation="建议"
        )
        assert result.data == []
        assert result.latency_ms == 0
        assert result.tokens_used == 0

class TestDashboardResponse:
    """测试仪表盘响应模型"""
    
    def test_valid_dashboard(self):
        """测试有效仪表盘响应"""
        response = DashboardResponse(
            total_coupons=1000,
            total_redemptions=500,
            redemption_rate=50.0,
            coupon_performance=[
                {"value": 10, "count": 100, "redemption_rate": 75.0}
            ],
            driver_stats={
                "total_drivers": 50,
                "active_drivers": 40
            }
        )
        assert response.total_coupons == 1000
        assert response.redemption_rate == 50.0
    
    def test_empty_dashboard(self):
        """测试空仪表盘响应"""
        response = DashboardResponse(
            total_coupons=0,
            total_redemptions=0,
            redemption_rate=0.0,
            coupon_performance=[],
            driver_stats={}
        )
        assert response.total_coupons == 0
        assert response.coupon_performance == []