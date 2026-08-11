from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2048)


class SQLResult(BaseModel):
    sql: str
    explanation: str
    data: list[dict] = []
    columns: list[str] = []


class AnalysisResult(BaseModel):
    question: str
    sql: str
    summary: str
    insight: str
    recommendation: str
    data: list[dict] = []
    latency_ms: float = 0
    tokens_used: int = 0


class DashboardResponse(BaseModel):
    total_coupons: int
    total_redemptions: int
    redemption_rate: float
    coupon_performance: list[dict]
    driver_stats: dict
    # 以下字段为前端图表提供真实数据（兼容旧调用，默认空容器）
    total_drivers: int = 0
    order_amount_distribution: list[dict] = []
    coupon_value_distribution: list[dict] = []
    redemption_status: dict = {}
    order_trend_14d: list[dict] = []
    redemption_trend_14d: list[dict] = []
    driver_activity: list[dict] = []
