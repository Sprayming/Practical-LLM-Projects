from fastapi import APIRouter, HTTPException
from loguru import logger

from app.anomaly.detector import anomaly_detector

router = APIRouter(prefix="/api/anomaly", tags=["Anomaly Detection"])


@router.get("/detect")
async def detect_anomalies():
    """检测所有异常"""
    try:
        anomalies = anomaly_detector.detect_all()
        return {
            "total": len(anomalies),
            "anomalies": anomalies
        }
    except Exception as e:
        logger.error("异常检测失败: {}", e)
        raise HTTPException(status_code=500, detail="异常检测失败")


@router.get("/summary")
async def get_anomaly_summary():
    """获取异常摘要"""
    try:
        summary = anomaly_detector.get_anomaly_summary()
        return summary
    except Exception as e:
        logger.error("获取异常摘要失败: {}", e)
        raise HTTPException(status_code=500, detail="获取异常摘要失败")


@router.get("/health")
async def health_check():
    """系统健康检查"""
    try:
        summary = anomaly_detector.get_anomaly_summary()
        
        # 根据异常数量判断健康状态
        if summary["critical"] > 0:
            status = "unhealthy"
            message = f"发现 {summary['critical']} 个严重异常"
        elif summary["warning"] > 0:
            status = "degraded"
            message = f"发现 {summary['warning']} 个警告"
        else:
            status = "healthy"
            message = "系统运行正常"
        
        return {
            "status": status,
            "message": message,
            "anomaly_count": summary["total"],
            "critical_count": summary["critical"],
            "warning_count": summary["warning"],
        }
    except Exception as e:
        logger.error("健康检查失败: {}", e)
        return {
            "status": "unknown",
            "message": f"健康检查失败: {str(e)}",
        }