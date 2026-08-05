from fastapi import APIRouter, HTTPException, Query, Depends
from fastapi.responses import StreamingResponse
from loguru import logger
from typing import Optional, List
from datetime import datetime
import csv
import io
import json

from app.history.models import (
    QueryHistoryCreate,
    QueryHistoryResponse,
    QueryHistoryListResponse,
    ExportFormat
)
from app.history.database import (
    create_query_history,
    get_query_history,
    list_query_history,
    update_query_history,
    toggle_favorite,
    delete_query_history,
    get_query_stats
)
from app.auth.dependencies import get_current_user_optional

router = APIRouter(prefix="/api/history", tags=["Query History"])


@router.post("/", response_model=QueryHistoryResponse, status_code=201)
async def create_history(history: QueryHistoryCreate):
    """创建查询历史记录"""
    try:
        history_dict = history.model_dump()
        history_id = create_query_history(history_dict)
        
        if history_id is None:
            raise HTTPException(status_code=500, detail="创建查询历史失败")
        
        created = get_query_history(history_id)
        return created
    except HTTPException:
        raise
    except Exception as e:
        logger.error("创建查询历史失败: {}", e)
        raise HTTPException(status_code=500, detail="创建查询历史失败")


@router.get("/", response_model=QueryHistoryListResponse)
async def list_history(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    status: Optional[str] = Query(None, description="状态筛选"),
    is_favorite: Optional[bool] = Query(None, description="收藏筛选"),
    search: Optional[str] = Query(None, description="搜索关键词")
):
    """列出查询历史"""
    try:
        items, total = list_query_history(
            page=page,
            page_size=page_size,
            status=status,
            is_favorite=is_favorite,
            search=search
        )
        
        return QueryHistoryListResponse(
            total=total,
            items=items,
            page=page,
            page_size=page_size
        )
    except Exception as e:
        logger.error("获取查询历史列表失败: {}", e)
        raise HTTPException(status_code=500, detail="获取查询历史失败")


@router.get("/stats")
async def get_stats():
    """获取查询统计"""
    try:
        stats = get_query_stats()
        return stats
    except Exception as e:
        logger.error("获取查询统计失败: {}", e)
        raise HTTPException(status_code=500, detail="获取统计失败")


@router.get("/{history_id}", response_model=QueryHistoryResponse)
async def get_history(history_id: int):
    """获取单条查询历史"""
    try:
        history = get_query_history(history_id)
        
        if history is None:
            raise HTTPException(status_code=404, detail="查询历史不存在")
        
        return history
    except HTTPException:
        raise
    except Exception as e:
        logger.error("获取查询历史失败: {}", e)
        raise HTTPException(status_code=500, detail="获取查询历史失败")


@router.put("/{history_id}/favorite")
async def toggle_history_favorite(history_id: int):
    """切换收藏状态"""
    try:
        new_status = toggle_favorite(history_id)
        
        if new_status is None:
            raise HTTPException(status_code=404, detail="查询历史不存在")
        
        return {
            "id": history_id,
            "is_favorite": new_status,
            "message": "收藏状态已更新"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("切换收藏状态失败: {}", e)
        raise HTTPException(status_code=500, detail="切换收藏状态失败")


@router.delete("/{history_id}")
async def delete_history(history_id: int):
    """删除查询历史"""
    try:
        success = delete_query_history(history_id)
        
        if not success:
            raise HTTPException(status_code=404, detail="查询历史不存在")
        
        return {"message": "删除成功"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("删除查询历史失败: {}", e)
        raise HTTPException(status_code=500, detail="删除查询历史失败")


@router.get("/export/{format}")
async def export_history(
    format: ExportFormat,
    query_ids: Optional[List[int]] = Query(None, description="指定导出的记录ID"),
    include_metadata: bool = Query(True, description="是否包含元数据")
):
    """导出查询历史"""
    try:
        # 获取要导出的数据
        if query_ids:
            items = []
            for qid in query_ids:
                item = get_query_history(qid)
                if item:
                    items.append(item)
        else:
            items, _ = list_query_history(page=1, page_size=10000)
        
        if not items:
            raise HTTPException(status_code=404, detail="没有可导出的数据")
        
        # 根据格式导出
        if format == ExportFormat.CSV:
            return _export_csv(items, include_metadata)
        elif format == ExportFormat.JSON:
            return _export_json(items, include_metadata)
        elif format == ExportFormat.EXCEL:
            # Excel需要额外的库，这里返回CSV作为替代
            return _export_csv(items, include_metadata, filename="export.xlsx")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("导出查询历史失败: {}", e)
        raise HTTPException(status_code=500, detail="导出失败")


def _export_csv(items: List[dict], include_metadata: bool, filename: str = None):
    """导出为CSV"""
    output = io.StringIO()
    writer = csv.writer(output)
    
    # 写入表头
    if include_metadata:
        headers = ["ID", "问题", "SQL", "摘要", "洞察", "建议", "状态", "延迟(ms)", "创建时间"]
    else:
        headers = ["问题", "SQL", "摘要", "洞察", "建议"]
    
    writer.writerow(headers)
    
    # 写入数据
    for item in items:
        if include_metadata:
            row = [
                item.get("id"),
                item.get("question"),
                item.get("sql"),
                item.get("summary"),
                item.get("insight"),
                item.get("recommendation"),
                item.get("status"),
                item.get("latency_ms"),
                item.get("created_at")
            ]
        else:
            row = [
                item.get("question"),
                item.get("sql"),
                item.get("summary"),
                item.get("insight"),
                item.get("recommendation")
            ]
        writer.writerow(row)
    
    # 返回文件
    output.seek(0)
    filename = filename or f"query_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


def _export_json(items: List[dict], include_metadata: bool):
    """导出为JSON"""
    if not include_metadata:
        # 只保留核心字段
        items = [
            {
                "question": item.get("question"),
                "sql": item.get("sql"),
                "summary": item.get("summary"),
                "insight": item.get("insight"),
                "recommendation": item.get("recommendation")
            }
            for item in items
        ]
    
    content = json.dumps(items, ensure_ascii=False, indent=2, default=str)
    filename = f"query_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    
    return StreamingResponse(
        iter([content]),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )