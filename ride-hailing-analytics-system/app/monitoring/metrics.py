from prometheus_client import Counter, Histogram, Gauge, Summary, generate_latest, CONTENT_TYPE_LATEST
from fastapi import APIRouter
from starlette.responses import Response
from loguru import logger
import time
import psutil
import os
from datetime import datetime

router = APIRouter(prefix="/api/monitoring", tags=["Monitoring"])

# ==================== 指标定义 ====================

# 请求计数器
REQUEST_COUNT = Counter(
    'app_requests_total',
    'Total number of requests',
    ['method', 'endpoint', 'status_code']
)

# 请求延迟直方图
REQUEST_LATENCY = Histogram(
    'app_request_latency_seconds',
    'Request latency in seconds',
    ['method', 'endpoint'],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
)

# SQL查询计数器
SQL_QUERY_COUNT = Counter(
    'app_sql_queries_total',
    'Total number of SQL queries',
    ['status']  # success, error
)

# SQL查询延迟
SQL_QUERY_LATENCY = Histogram(
    'app_sql_query_latency_seconds',
    'SQL query latency in seconds',
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0]
)

# LLM调用计数器
LLM_CALL_COUNT = Counter(
    'app_llm_calls_total',
    'Total number of LLM API calls',
    ['status']  # success, error
)

# LLM调用延迟
LLM_CALL_LATENCY = Histogram(
    'app_llm_call_latency_seconds',
    'LLM API call latency in seconds',
    buckets=[0.5, 1.0, 2.5, 5.0, 10.0, 30.0]
)

# LLM Token使用量
LLM_TOKEN_USAGE = Counter(
    'app_llm_tokens_total',
    'Total tokens used in LLM calls',
    ['type']  # prompt, completion
)

# 活跃查询数
ACTIVE_QUERIES = Gauge(
    'app_active_queries',
    'Number of currently active queries'
)

# 数据库连接数
DB_CONNECTIONS = Gauge(
    'app_db_connections',
    'Number of database connections'
)

# 系统指标
SYSTEM_CPU_USAGE = Gauge(
    'app_system_cpu_usage_percent',
    'CPU usage percentage'
)

SYSTEM_MEMORY_USAGE = Gauge(
    'app_system_memory_usage_percent',
    'Memory usage percentage'
)

SYSTEM_DISK_USAGE = Gauge(
    'app_system_disk_usage_percent',
    'Disk usage percentage'
)

# 应用启动时间
APP_START_TIME = Gauge(
    'app_start_time_seconds',
    'Application start time in seconds'
)

# 记录启动时间
APP_START_TIME.set(time.time())


# ==================== 指标记录函数 ====================

def record_request(method: str, endpoint: str, status_code: int, latency: float):
    """记录请求指标"""
    REQUEST_COUNT.labels(method=method, endpoint=endpoint, status_code=str(status_code)).inc()
    REQUEST_LATENCY.labels(method=method, endpoint=endpoint).observe(latency)


def record_sql_query(status: str, latency: float):
    """记录SQL查询指标"""
    SQL_QUERY_COUNT.labels(status=status).inc()
    SQL_QUERY_LATENCY.observe(latency)


def record_llm_call(status: str, latency: float, prompt_tokens: int = 0, completion_tokens: int = 0):
    """记录LLM调用指标"""
    LLM_CALL_COUNT.labels(status=status).inc()
    LLM_CALL_LATENCY.observe(latency)
    if prompt_tokens > 0:
        LLM_TOKEN_USAGE.labels(type='prompt').inc(prompt_tokens)
    if completion_tokens > 0:
        LLM_TOKEN_USAGE.labels(type='completion').inc(completion_tokens)


def update_system_metrics():
    """更新系统指标"""
    try:
        # CPU使用率
        cpu_percent = psutil.cpu_percent(interval=0.1)
        SYSTEM_CPU_USAGE.set(cpu_percent)
        
        # 内存使用率
        memory = psutil.virtual_memory()
        SYSTEM_MEMORY_USAGE.set(memory.percent)
        
        # 磁盘使用率
        disk = psutil.disk_usage('/')
        SYSTEM_DISK_USAGE.set(disk.percent)
    except Exception as e:
        logger.warning("更新系统指标失败: {}", e)


# ==================== API端点 ====================

@router.get("/metrics")
async def metrics():
    """Prometheus指标端点"""
    update_system_metrics()
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST
    )


@router.get("/health")
async def health_check():
    """健康检查端点"""
    import sqlite3
    from pathlib import Path
    
    health_status = {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "0.2.0",
        "checks": {}
    }
    
    # 检查数据库
    try:
        db_path = Path(__file__).resolve().parent.parent.parent / "data" / "ride_hailing.db"
        conn = sqlite3.connect(str(db_path), timeout=5)
        cursor = conn.execute("SELECT 1")
        cursor.fetchone()
        conn.close()
        health_status["checks"]["database"] = {"status": "healthy"}
    except Exception as e:
        health_status["checks"]["database"] = {"status": "unhealthy", "error": str(e)}
        health_status["status"] = "degraded"
    
    # 检查系统资源
    try:
        cpu_percent = psutil.cpu_percent(interval=0.1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        health_status["checks"]["system"] = {
            "status": "healthy",
            "cpu_percent": cpu_percent,
            "memory_percent": memory.percent,
            "disk_percent": disk.percent
        }
        
        # 如果资源使用率过高，标记为降级
        if cpu_percent > 90 or memory.percent > 90 or disk.percent > 90:
            health_status["status"] = "degraded"
            health_status["checks"]["system"]["status"] = "warning"
    except Exception as e:
        health_status["checks"]["system"] = {"status": "unknown", "error": str(e)}
    
    # 检查LLM配置
    try:
        from app.config import settings
        if settings.llm_api_key:
            health_status["checks"]["llm"] = {"status": "configured"}
        else:
            health_status["checks"]["llm"] = {"status": "not_configured"}
    except Exception:
        health_status["checks"]["llm"] = {"status": "unknown"}
    
    return health_status


@router.get("/stats")
async def app_stats():
    """应用统计端点"""
    try:
        import sqlite3
        from pathlib import Path
        
        db_path = Path(__file__).resolve().parent.parent.parent / "data" / "ride_hailing.db"
        conn = sqlite3.connect(str(db_path))
        
        stats = {
            "timestamp": datetime.now().isoformat(),
            "uptime_seconds": time.time() - APP_START_TIME._value.get(),
        }
        
        # 获取数据统计
        try:
            cursor = conn.execute("SELECT COUNT(*) FROM drivers")
            stats["total_drivers"] = cursor.fetchone()[0]
        except:
            stats["total_drivers"] = 0
        
        try:
            cursor = conn.execute("SELECT COUNT(*) FROM orders")
            stats["total_orders"] = cursor.fetchone()[0]
        except:
            stats["total_orders"] = 0
        
        try:
            cursor = conn.execute("SELECT COUNT(*) FROM coupons")
            stats["total_coupons"] = cursor.fetchone()[0]
        except:
            stats["total_coupons"] = 0
        
        try:
            cursor = conn.execute("SELECT COUNT(*) FROM redemptions")
            stats["total_redemptions"] = cursor.fetchone()[0]
        except:
            stats["total_redemptions"] = 0
        
        conn.close()
        
        return stats
    except Exception as e:
        return {"error": str(e)}