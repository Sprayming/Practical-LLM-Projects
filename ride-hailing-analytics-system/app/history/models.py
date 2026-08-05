from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


class QueryStatus(str, Enum):
    """查询状态枚举"""
    SUCCESS = "success"
    ERROR = "error"
    PENDING = "pending"


class QueryHistory(BaseModel):
    """查询历史模型"""
    id: Optional[int] = None
    question: str
    sql: Optional[str] = None
    summary: Optional[str] = None
    insight: Optional[str] = None
    recommendation: Optional[str] = None
    data: Optional[List[dict]] = None
    status: QueryStatus = QueryStatus.SUCCESS
    error_message: Optional[str] = None
    latency_ms: Optional[float] = None
    tokens_used: Optional[int] = None
    is_favorite: bool = False
    created_at: Optional[datetime] = None


class QueryHistoryCreate(BaseModel):
    """创建查询历史请求"""
    question: str
    sql: Optional[str] = None
    summary: Optional[str] = None
    insight: Optional[str] = None
    recommendation: Optional[str] = None
    data: Optional[List[dict]] = None
    status: QueryStatus = QueryStatus.SUCCESS
    error_message: Optional[str] = None
    latency_ms: Optional[float] = None
    tokens_used: Optional[int] = None


class QueryHistoryResponse(BaseModel):
    """查询历史响应"""
    id: int
    question: str
    sql: Optional[str]
    summary: Optional[str]
    insight: Optional[str]
    recommendation: Optional[str]
    data: Optional[List[dict]]
    status: QueryStatus
    error_message: Optional[str]
    latency_ms: Optional[float]
    tokens_used: Optional[int]
    is_favorite: bool
    created_at: datetime


class QueryHistoryListResponse(BaseModel):
    """查询历史列表响应"""
    total: int
    items: List[QueryHistoryResponse]
    page: int
    page_size: int


class ExportFormat(str, Enum):
    """导出格式枚举"""
    CSV = "csv"
    EXCEL = "excel"
    JSON = "json"


class ExportRequest(BaseModel):
    """导出请求"""
    query_ids: Optional[List[int]] = None
    format: ExportFormat = ExportFormat.CSV
    include_metadata: bool = True