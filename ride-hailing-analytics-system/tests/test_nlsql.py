import pytest
from unittest.mock import patch, MagicMock
from app.nlsql.sql_generator import generate_sql, SYSTEM_PROMPT
from app.nlsql.schema_parser import describe_tables
from app.nlsql.sql_executor import validate_sql, run_sql

class TestSQLGenerator:
    """测试SQL生成器"""
    
    def test_system_prompt_format(self):
        """测试系统提示格式"""
        prompt = SYSTEM_PROMPT.format(table_schema="test schema")
        assert "SQL 分析师" in prompt
        assert "test schema" in prompt
        assert "SELECT" in prompt
    
    @patch('app.nlsql.sql_generator.OpenAI')
    def test_generate_sql_success(self, mock_openai):
        """测试SQL生成成功"""
        # 模拟LLM响应
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = """
        SELECT ct.value, COUNT(r.id) as count
        FROM coupon_types ct
        JOIN coupons c ON c.coupon_type_id = ct.id
        LEFT JOIN redemptions r ON r.coupon_id = c.id
        GROUP BY ct.id, ct.value
        
        这个SQL查询统计了不同面值卡券的核销数量
        """
        mock_openai.return_value.chat.completions.create.return_value = mock_response
        
        # 调用测试
        sql, explanation = generate_sql("哪个价位的卡券核销率最高？")
        
        assert sql is not None
        assert "SELECT" in sql
        assert explanation is not None
    
    def test_schema_parser(self):
        """测试Schema解析器"""
        schema = describe_tables()
        # 测试返回的是字符串
        assert isinstance(schema, str)
        # 测试包含表信息
        assert "drivers" in schema or "coupon_types" in schema

class TestSQLValidator:
    """测试SQL验证器"""
    
    def test_validate_select_query(self):
        """测试验证SELECT查询"""
        sql = "SELECT * FROM drivers"
        assert validate_sql(sql) is True
    
    def test_validate_complex_select(self):
        """测试验证复杂SELECT查询"""
        sql = """
        SELECT d.name, COUNT(o.id) as order_count
        FROM drivers d
        JOIN orders o ON o.driver_id = d.id
        WHERE o.created_at >= DATE_SUB(NOW(), INTERVAL 30 DAY)
        GROUP BY d.id, d.name
        ORDER BY order_count DESC
        LIMIT 10
        """
        assert validate_sql(sql) is True
    
    def test_reject_insert(self):
        """测试拒绝INSERT语句"""
        sql = "INSERT INTO drivers (name) VALUES ('test')"
        assert validate_sql(sql) is False
    
    def test_reject_update(self):
        """测试拒绝UPDATE语句"""
        sql = "UPDATE drivers SET name = 'test'"
        assert validate_sql(sql) is False
    
    def test_reject_delete(self):
        """测试拒绝DELETE语句"""
        sql = "DELETE FROM drivers WHERE id = 1"
        assert validate_sql(sql) is False
    
    def test_reject_drop(self):
        """测试拒绝DROP语句"""
        sql = "DROP TABLE drivers"
        assert validate_sql(sql) is False
    
    def test_reject_alter(self):
        """测试拒绝ALTER语句"""
        sql = "ALTER TABLE drivers ADD COLUMN test VARCHAR(100)"
        assert validate_sql(sql) is False
    
    def test_reject_truncate(self):
        """测试拒绝TRUNCATE语句"""
        sql = "TRUNCATE TABLE drivers"
        assert validate_sql(sql) is False
    
    def test_reject_create(self):
        """测试拒绝CREATE语句"""
        sql = "CREATE TABLE test (id INT)"
        assert validate_sql(sql) is False
    
    def test_case_insensitive(self):
        """测试大小写不敏感"""
        sql = "select * from drivers"
        assert validate_sql(sql) is True
        
        sql = "SELECT * FROM drivers"
        assert validate_sql(sql) is True
    
    def test_empty_sql(self):
        """测试空SQL"""
        sql = ""
        assert validate_sql(sql) is False
    
    def test_whitespace_only(self):
        """测试仅空白字符"""
        sql = "   \n\t  "
        assert validate_sql(sql) is False