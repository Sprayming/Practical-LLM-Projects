from __future__ import annotations
import time
from fastapi import APIRouter, HTTPException, Depends
from loguru import logger

from app.models import QueryRequest, AnalysisResult
from app.nlsql.sql_generator import generate_sql
from app.nlsql.sql_executor import run_sql
from app.analysis.interpreter import interpret
from app.analysis.recommender import recommend
from app.security.validators import sanitize_input, validate_question
from app.security.error_handlers import ValidationError, DatabaseError, LLMError
from app.auth.dependencies import get_current_user_optional

router = APIRouter(prefix="/api/query", tags=["Query"])


@router.post("/", response_model=AnalysisResult)
async def natural_language_query(request: QueryRequest):
    """自然语言查询接口"""
    start = time.perf_counter()
    
    try:
        # 输入验证
        question = sanitize_input(request.question)
        is_valid, error_msg = validate_question(question)
        if not is_valid:
            raise ValidationError(error_msg, "INVALID_QUESTION")
        
        # 生成SQL
        try:
            sql, explanation = generate_sql(question)
        except Exception as e:
            logger.error("SQL生成失败: {}", e)
            raise LLMError("SQL生成失败，请稍后重试", "SQL_GENERATION_FAILED")
        
        if not sql:
            raise ValidationError("无法生成有效的SQL查询", "NO_SQL_GENERATED")
        
        # 执行SQL
        try:
            rows, columns = run_sql(sql)
        except Exception as e:
            logger.error("SQL执行失败: {}", e)
            raise DatabaseError("数据库查询失败，请稍后重试", "SQL_EXECUTION_FAILED")
        
        # 数据分析
        try:
            summary = interpret(question, sql, rows)
        except Exception as e:
            logger.warning("数据分析失败: {}", e)
            summary = f"数据查询完成，共返回 {len(rows)} 条记录"
        
        # 生成建议
        try:
            advice = recommend(question, rows)
        except Exception as e:
            logger.warning("建议生成失败: {}", e)
            advice = "暂无具体建议"
        
        elapsed = (time.perf_counter() - start) * 1000
        
        return AnalysisResult(
            question=question,
            sql=sql,
            summary=summary,
            insight=explanation,
            recommendation=advice,
            data=rows[:100],
            latency_ms=round(elapsed, 2),
        )
    
    except (ValidationError, DatabaseError, LLMError):
        raise
    except Exception as e:
        logger.error("查询失败: {}", e)
        raise HTTPException(status_code=500, detail="查询失败，请稍后重试")
