import pytest
import os
import sys
from pathlib import Path

# 添加项目根目录到Python路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import Settings

@pytest.fixture(scope="session")
def test_settings():
    """测试配置"""
    return Settings(
        db_host="127.0.0.1",
        db_port=3306,
        db_name="test_ride_hailing",
        db_user="root",
        db_password="",
        llm_api_key="test-key",
        llm_base_url="https://api.deepseek.com/v1",
        llm_model="deepseek-chat",
        llm_temperature=0.05,
        debug=True
    )

@pytest.fixture(scope="session")
def sample_question():
    """示例问题"""
    return "哪个价位的卡券核销率最高？"

@pytest.fixture(scope="session")
def sample_sql():
    """示例SQL"""
    return """
    SELECT 
        ct.value as coupon_value,
        COUNT(r.id) as redemption_count,
        COUNT(DISTINCT c.id) as coupon_count,
        ROUND(COUNT(r.id) * 100.0 / COUNT(DISTINCT c.id), 2) as redemption_rate
    FROM coupon_types ct
    JOIN coupons c ON c.coupon_type_id = ct.id
    LEFT JOIN redemptions r ON r.coupon_id = c.id
    GROUP BY ct.id, ct.value
    ORDER BY redemption_rate DESC
    """

@pytest.fixture(scope="session")
def sample_data():
    """示例数据"""
    return [
        {"coupon_value": 10, "redemption_count": 150, "coupon_count": 200, "redemption_rate": 75.0},
        {"coupon_value": 20, "redemption_count": 120, "coupon_count": 180, "redemption_rate": 66.67},
        {"coupon_value": 50, "redemption_count": 80, "coupon_count": 150, "redemption_rate": 53.33},
    ]