from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from loguru import logger
from typing import Optional
from datetime import datetime
import io

from app.report.generator import report_generator

router = APIRouter(prefix="/api/report", tags=["Report"])


@router.get("/generate")
async def generate_report(
    period: str = Query("week", description="报告周期：week/month"),
    format: str = Query("markdown", description="输出格式：markdown/html")
):
    """生成运营报告"""
    try:
        if period not in ["week", "month"]:
            raise HTTPException(status_code=400, detail="周期参数无效，支持 week/month")
        
        # 生成报告
        report_content = report_generator.generate_report(period)
        
        # 根据格式返回
        if format == "html":
            # 简单的Markdown转HTML
            html_content = _markdown_to_html(report_content)
            return StreamingResponse(
                iter([html_content]),
                media_type="text/html",
                headers={
                    "Content-Disposition": f"attachment; filename=report_{period}_{datetime.now().strftime('%Y%m%d')}.html"
                }
            )
        else:
            return StreamingResponse(
                iter([report_content]),
                media_type="text/markdown",
                headers={
                    "Content-Disposition": f"attachment; filename=report_{period}_{datetime.now().strftime('%Y%m%d')}.md"
                }
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("生成报告失败: {}", e)
        raise HTTPException(status_code=500, detail="生成报告失败")


@router.get("/metrics")
async def get_metrics(days: int = Query(7, ge=1, le=90, description="统计天数")):
    """获取核心指标"""
    try:
        metrics = report_generator.get_core_metrics(days)
        return {
            "period_days": days,
            "metrics": metrics
        }
    except Exception as e:
        logger.error("获取指标失败: {}", e)
        raise HTTPException(status_code=500, detail="获取指标失败")


@router.get("/trend")
async def get_trend(days: int = Query(7, ge=1, le=30, description="趋势天数")):
    """获取趋势数据"""
    try:
        trend = report_generator.get_trend_data(days)
        return {
            "period_days": days,
            "trend": trend
        }
    except Exception as e:
        logger.error("获取趋势失败: {}", e)
        raise HTTPException(status_code=500, detail="获取趋势失败")


@router.get("/coupon-analysis")
async def get_coupon_analysis():
    """获取卡券分析"""
    try:
        analysis = report_generator.get_coupon_analysis()
        return {
            "analysis": analysis
        }
    except Exception as e:
        logger.error("获取卡券分析失败: {}", e)
        raise HTTPException(status_code=500, detail="获取卡券分析失败")


@router.get("/top-drivers")
async def get_top_drivers(limit: int = Query(10, ge=1, le=50, description="返回数量")):
    """获取TOP司机"""
    try:
        from app.report.generator import get_top_drivers
        drivers = get_top_drivers(limit)
        return {
            "limit": limit,
            "drivers": drivers
        }
    except Exception as e:
        logger.error("获取TOP司机失败: {}", e)
        raise HTTPException(status_code=500, detail="获取TOP司机失败")


@router.get("/hourly-distribution")
async def get_hourly_distribution():
    """获取时段分布"""
    try:
        from app.report.generator import get_hourly_distribution
        distribution = get_hourly_distribution()
        return {
            "distribution": distribution
        }
    except Exception as e:
        logger.error("获取时段分布失败: {}", e)
        raise HTTPException(status_code=500, detail="获取时段分布失败")


def _markdown_to_html(markdown: str) -> str:
    """简单的Markdown转HTML"""
    html = markdown
    
    # 标题
    html = html.replace("# ", "<h1>").replace("\n", "</h1>\n", 1)
    html = html.replace("## ", "<h2>")
    html = html.replace("### ", "<h3>")
    
    # 表格
    lines = html.split("\n")
    in_table = False
    new_lines = []
    
    for line in lines:
        if "|" in line and "---" not in line:
            if not in_table:
                new_lines.append("<table>")
                in_table = True
            cells = [c.strip() for c in line.split("|") if c.strip()]
            new_lines.append("<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>")
        else:
            if in_table:
                new_lines.append("</table>")
                in_table = False
            new_lines.append(line)
    
    if in_table:
        new_lines.append("</table>")
    
    return "\n".join(new_lines)