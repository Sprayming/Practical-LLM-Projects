from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from app.data import get_orders, get_datasets, get_dataset_info
from app.analysis.statistics import compute_kpi
from app.analysis.trends import daily_trends
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

def _build_context_data():
    """构建 AI 问答的上下文（支持多 Sheet）"""
    orders = get_orders()
    if orders:
        kpi = compute_kpi(orders)
        trends = daily_trends(orders)
        anomalies = detect_anomalies(orders, settings.anomaly_threshold)
        lines = [
            f"订单数据：共{len(orders)}条，{kpi.get('active_drivers',0)}位司机",
            f"完成{kpi.get('completed_orders',0)}单，收入{kpi.get('total_revenue',0)}元",
        ]
        if anomalies:
            for a in anomalies[:3]:
                lines.append(f"异常：{a['date']} {a['metric']} ({a['severity']})")
        return "\n".join(lines)

    info = get_dataset_info()
    if info:
        lines = [f"共 {len(info)} 个数据表："]
        for name, ds in info.items():
            cols = ", ".join(ds["columns"][:6])
            lines.append(f"  [{name}]: {ds['count']}行, {len(ds['columns'])}列 ({cols})")
        return "\n".join(lines)

    return "暂无数据"

@router.post("/ask", response_model=AskResponse)
async def ask_question(req: AskRequest):
    orders = get_orders()
    ds_info = get_dataset_info()
    if not orders and not ds_info:
        raise HTTPException(400, "暂无数据，请先上传数据文件")

    context = _build_context_data()
    data_type = "orders" if orders else "dataset"
    analyst = get_analyst()
    answer = analyst.ask_question(req.query, context)

    return AskResponse(success=True, answer=answer, data_type=data_type)

@router.post("/run")
async def run_analysis(date_start: str = "", date_end: str = ""):
    from app.data.preprocessor import filter_by_date
    orders = get_orders()
    if not orders:
        ds_info = get_dataset_info()
        if ds_info:
            return {"success": True, "type": "dataset", "sheets": {n: d["count"] for n,d in ds_info.items()},
                    "message": f"已加载 {len(ds_info)} 个数据表，可在聊天框提问"}
        raise HTTPException(400, "暂无数据")
    
    filtered = filter_by_date(orders, date_start, date_end)
    if not filtered:
        raise HTTPException(400, "指定日期范围内没有数据")

    from app.analysis.statistics import revenue_analysis
    from app.analysis.trends import weekly_pattern, hour_heatmap
    kpi = compute_kpi(filtered)
    revenue = revenue_analysis(filtered)
    trends = daily_trends(filtered)
    weekly = weekly_pattern(filtered)
    heatmap = hour_heatmap(filtered)
    anomalies = detect_anomalies(filtered, settings.anomaly_threshold)

    stats = f"共{len(filtered)}条, 完成{kpi.get('completed_orders',0)}单, 收入{kpi.get('total_revenue',0)}元"
    trend = f"日均{round(sum(t['value'] for t in trends)/len(trends),1)}单" if trends else ""
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
    if not orders: return {"data": []}
    t = daily_trends(orders)
    return {"data": t[-days:]}

@router.get("/anomalies")
async def get_anomalies(days: int = 30, threshold: float = 2.0):
    orders = get_orders()
    if not orders: return {"anomalies": []}
    return {"anomalies": detect_anomalies(orders, threshold)}