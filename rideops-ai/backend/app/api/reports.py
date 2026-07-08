from fastapi import APIRouter
from app.data import get_orders
from app.analysis.statistics import compute_kpi, revenue_analysis
from app.analysis.trends import daily_trends, weekly_pattern
from app.analysis.anomalies import detect_anomalies
from app.config import settings

router = APIRouter(prefix="/api/reports", tags=["Reports"])

_reports: list = []


@router.post("/generate")
async def generate_report():
    """生成运营报告"""
    orders = get_orders()
    if not orders:
        return {"success": False, "message": "暂无数据"}

    kpi = compute_kpi(orders)
    revenue = revenue_analysis(orders)
    trends = daily_trends(orders)
    weekly = weekly_pattern(orders)
    anomalies = detect_anomalies(orders, settings.anomaly_threshold)

    report = {
        "id": f"RPT-{len(_reports)+1:04d}",
        "kpi": kpi,
        "revenue": revenue,
        "trends": trends,
        "weekly": weekly,
        "anomalies": anomalies,
    }
    _reports.append(report)

    return {"success": True, "report": report}


@router.get("/list")
async def list_reports():
    """列出历史报告"""
    return {"reports": _reports, "total": len(_reports)}
