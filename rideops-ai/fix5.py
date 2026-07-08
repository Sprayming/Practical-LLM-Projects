import os

root = "D:/git/rideops-ai/backend/app"

analysis_code = r'''
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
from app.data import get_orders, get_dataset
from app.data.preprocessor import filter_by_date
from app.analysis.statistics import compute_kpi, revenue_analysis
from app.analysis.trends import daily_trends, weekly_pattern, hour_heatmap
from app.analysis.anomalies import detect_anomalies
from app.ai.analyst import get_analyst
from app.config import settings

router = APIRouter(prefix="/api/analysis", tags=["Analysis"])


class AskRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=1024)


class AskResponse(BaseModel):
    success: bool
    answer: str
    data_type: str = "unknown"


def _format_dataset_context():
    """将通用数据集格式化为 AI 可读的上下文"""
    ds = get_dataset()
    if ds["count"] == 0:
        return "暂无数据"

    cols = ds["columns"]
    rows = ds["rows"]
    lines = [
        f"数据总览：共 {ds['count']} 行数据，{len(cols)} 列",
        f"列名：{', '.join(cols)}",
        f"前5行示例：",
    ]
    for i, row in enumerate(rows[:5]):
        vals = {k: v for k, v in row.items() if v is not None}
        lines.append(f"  行{i+1}: {vals}")
    return "\n".join(lines)


def _build_context_data():
    """构建 AI 问答的上下文"""
    orders = get_orders()
    if orders:
        from app.analysis.statistics import compute_kpi
        from app.analysis.trends import daily_trends
        from app.analysis.anomalies import detect_anomalies
        kpi = compute_kpi(orders)
        trends = daily_trends(orders)
        anomalies = detect_anomalies(orders, settings.anomaly_threshold)
        lines = [
            f"订单数据：共{len(orders)}条，{kpi.get('active_drivers',0)}位司机",
            f"完成{kpi.get('completed_orders',0)}单，收入{kpi.get('total_revenue',0)}元",
            f"平均评分{kpi.get('avg_rating',0)}，高峰{kpi.get('peak_hour','')}",
        ]
        if anomalies:
            for a in anomalies:
                lines.append(f"异常：{a['date']} {a['metric']}")
        return "\n".join(lines)

    ds = get_dataset()
    if ds["count"] > 0:
        return _format_dataset_context()
    return "暂无数据，请先上传数据文件"


@router.post("/ask", response_model=AskResponse)
async def ask_question(req: AskRequest):
    orders = get_orders()
    ds = get_dataset()
    if not orders and ds["count"] == 0:
        raise HTTPException(400, "暂无数据，请先上传数据文件")

    context = _build_context_data()
    data_type = "orders" if orders else "dataset"
    analyst = get_analyst()
    answer = analyst.ask_question(req.query, context)

    return AskResponse(success=True, answer=answer, data_type=data_type)


@router.post("/run")
async def run_analysis(date_start: str = "", date_end: str = ""):
    orders = get_orders()
    if not orders:
        ds = get_dataset()
        if ds["count"] > 0:
            return {
                "success": True,
                "type": "dataset",
                "message": f"已加载 {ds['count']} 行数据，{len(ds['columns'])} 列。可在聊天框提问进行 AI 分析。",
                "columns": ds["columns"],
                "preview": ds["rows"][:5],
            }
        raise HTTPException(400, "暂无数据，请先上传数据文件")

    filtered = filter_by_date(orders, date_start, date_end)
    if not filtered:
        raise HTTPException(400, "指定日期范围内没有数据")

    kpi = compute_kpi(filtered)
    revenue = revenue_analysis(filtered)
    trends = daily_trends(filtered)
    weekly = weekly_pattern(filtered)
    heatmap = hour_heatmap(filtered)
    anomalies = detect_anomalies(filtered, settings.anomaly_threshold)

    stats = f"共{len(filtered)}条, 完成{kpi.get('completed_orders',0)}单, 收入{kpi.get('total_revenue',0)}元"
    trend = f"日均{round(sum(t['value'] for t in trends)/len(trends))}单" if trends else ""
    anom = f"检测到{len(anomalies)}个异常" if anomalies else "未发现异常"
    ai = get_analyst().generate_analysis(stats, trend, anom)

    return {
        "success": True, "type": "orders",
        "kpi": kpi, "revenue": revenue,
        "trends": trends, "weekly_pattern": weekly, "hour_heatmap": heatmap,
        "anomalies": anomalies, "ai_analysis": ai,
    }


@router.get("/trends")
async def get_trends(metric: str = "orders", days: int = 30):
    orders = get_orders()
    if not orders:
        return {"data": []}
    t = daily_trends(orders)
    return {"data": t[-days:]}


@router.get("/anomalies")
async def get_anomalies(days: int = 30, threshold: float = 2.0):
    orders = get_orders()
    if not orders:
        return {"anomalies": []}
    return {"anomalies": detect_anomalies(orders, threshold)}
'''

with open(root + "/api/analysis.py", "w", encoding="utf-8") as f:
    f.write(analysis_code.strip())

print("api/analysis.py 已重写")
