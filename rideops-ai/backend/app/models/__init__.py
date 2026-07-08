"""
数据模型 — 定义网约车运营数据和分析结果的格式
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


# ── 原始数据模型 ──────────────────────────────

class Order(BaseModel):
    """网约车订单数据"""
    order_id: str                          # 订单号
    driver_id: str                         # 司机 ID
    passenger_id: str                      # 乘客 ID
    pickup_time: datetime                  # 接单时间
    pickup_location: str                   # 上车地点
    dropoff_location: str                  # 下车地点
    distance_km: float                     # 行驶里程（公里）
    duration_min: int                      # 行驶时长（分钟）
    fare: float                            # 订单金额
    status: str                            # 状态：completed/cancelled
    rating: Optional[float] = None         # 乘客评分（1-5）
    created_at: datetime = Field(default_factory=datetime.now)


class Driver(BaseModel):
    """司机信息"""
    driver_id: str
    name: str
    city: str                              # 所在城市
    vehicle_type: str                      # 车辆类型
    join_date: datetime                    # 注册日期
    status: str                            # 在线/离线
    total_trips: int = 0                   # 累计订单数
    rating: float = 5.0                    # 平均评分
    revenue_total: float = 0.0             # 累计收入


class DailyStats(BaseModel):
    """每日运营统计"""
    date: str                              # 日期 yyyy-MM-dd
    total_orders: int                      # 总订单数
    completed_orders: int                  # 完成订单数
    cancelled_orders: int                  # 取消订单数
    total_revenue: float                   # 总收入
    avg_fare: float                        # 平均客单价
    active_drivers: int                    # 活跃司机数
    avg_rating: float                      # 平均评分
    peak_hour: int                         # 订单高峰时段


# ── 分析结果模型 ──────────────────────────────

class TrendPoint(BaseModel):
    """趋势数据点"""
    date: str
    value: float
    change_rate: float = 0.0               # 环比变化率


class AnomalyResult(BaseModel):
    """异常检测结果"""
    date: str
    metric: str                            # 异常指标名称
    actual_value: float                    # 实际值
    expected_value: float                   # 预期值
    deviation: float                       # 偏离程度
    severity: str                          # 严重程度 high/medium/low
    suggestion: str                        # 建议处理方式


class AnalysisReport(BaseModel):
    """完整分析报告"""
    report_id: str
    generated_at: datetime = Field(default_factory=datetime.now)
    date_range: str                        # 分析时间段
    summary: str                           # AI 生成的总结
    key_metrics: dict                      # 关键指标摘要
    trends: List[TrendPoint]               # 趋势数据
    anomalies: List[AnomalyResult]         # 异常检测结果
    recommendations: List[str]             # AI 运营建议


# ── API 请求/响应模型 ─────────────────────────

class AnalysisRequest(BaseModel):
    """分析请求"""
    date_start: str                        # 开始日期
    date_end: str                          # 结束日期
    metrics: Optional[List[str]] = None    # 要分析的指标列表
    include_anomaly: bool = True           # 是否检测异常
    include_ai_analysis: bool = True       # 是否生成 AI 分析


class AnalysisResponse(BaseModel):
    """分析响应"""
    success: bool
    report: Optional[AnalysisReport] = None
    message: str = ""
