from __future__ import annotations
import time
from fastapi import APIRouter, HTTPException
from loguru import logger

from app.models import QueryRequest, AnalysisResult
from app.nlsql.sql_generator import generate_sql
from app.nlsql.sql_executor import run_sql
from app.analysis.interpreter import interpret
from app.analysis.recommender import recommend

router = APIRouter(prefix="/api/query", tags=["Query"])


@router.post("/", response_model=AnalysisResult)
async def natural_language_query(request: QueryRequest):
    start = time.perf_counter()
    
    try:
        sql, explanation = generate_sql(request.question)
        if not sql:
            raise HTTPException(status_code=400, detail="无法生成 SQL")
        
        rows, columns = run_sql(sql)
        
        summary = interpret(request.question, sql, rows)
        advice = recommend(request.question, rows)
        
        elapsed = (time.perf_counter() - start) * 1000
        
        return AnalysisResult(
            question=request.question,
            sql=sql,
            summary=summary,
            insight=explanation,
            recommendation=advice,
            data=rows[:100],
            latency_ms=round(elapsed, 2),
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error("查询失败: {}", e)
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")
