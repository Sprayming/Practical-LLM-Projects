"""
app/observability/monitoring.py —— 指标监控、健康检查与运行统计(FastAPI 路由)

【作用与功能】
提供与 Prometheus 兼容的监控能力:暴露 /metrics(Prometheus 文本格式指标)、
/health(含 Redis/磁盘/内存子系统检查的综合健康端点)、/stats(运行统计与追踪摘要)。
内置一个线程安全的轻量级指标收集器(MetricsCollector)，无需引入外部依赖即可在
进程内累计计数器、仪表盘与直方图，并支持导出为 Prometheus 文本或字典。

【主要组成】
- `MetricsCollector`:线程安全的进程内指标收集器(counter/gauge/histogram)
- `get_metrics_collector`:返回全局单例收集器
- `record_query` / `record_upload`:预置的指标上报辅助函数
- `_check_redis` / `_check_disk` / `_check_memory`:子系统健康检查
- `metrics` / `health` / `stats`:FastAPI 路由端点

【适用场景】
- 场景1:被 FastAPI 应用挂载为 /metrics、/health、/stats 监控端点
- 场景2:在查询/上传路径中调用 record_query / record_upload 上报指标
- 场景3:运维通过 Prometheus + Grafana 拉取 /metrics 做可视化告警

【依赖关系】
- 上游调用方:app 主服务(API 路由注册)
- 下游依赖:fastapi、psutil、loguru、app.core.config、app.observability.tracker
"""

"""
Monitoring module for Legal-DOC-RAG.

Provides:
- Prometheus-compatible /metrics endpoint
- Enhanced /health endpoint with subsystem checks
- Runtime statistics
"""
import os
import time
import threading
import psutil
from datetime import datetime
from typing import Dict, Any
from fastapi import APIRouter
from fastapi.responses import PlainTextResponse, JSONResponse
from loguru import logger


router = APIRouter(tags=["monitoring"])


# ============================================================
# Application Metrics Collector (lightweight, no external deps)
# ============================================================

class MetricsCollector:
    """线程安全的进程内指标收集器。

    以 Counter(只增计数)、Gauge(可设值仪表)、Histogram(采样分布)三类指标
    在内存中累计运行数据，并通过 threading.Lock 保证并发安全。所有导出方法均加锁
    读取，避免统计过程中数据不一致。实例通常作为全局单例使用(见 get_metrics_collector)。
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._start_time = time.time()
        self._counters: Dict[str, int] = {}
        self._gauges: Dict[str, float] = {}
        self._histograms: Dict[str, list] = {}

    def inc(self, name: str, value: int = 1):
        """Increment a counter."""
        with self._lock:
            self._counters[name] = self._counters.get(name, 0) + value

    def set(self, name: str, value: float):
        """Set a gauge value."""
        with self._lock:
            self._gauges[name] = value

    def observe(self, name: str, value: float):
        """Record a histogram observation."""
        with self._lock:
            if name not in self._histograms:
                self._histograms[name] = []
            self._histograms[name].append(value)
            # Keep only last 1000 observations
            if len(self._histograms[name]) > 1000:
                self._histograms[name] = self._histograms[name][-1000:]

    def to_prometheus(self) -> str:
        """Export metrics in Prometheus text format."""
        lines = []
        lines.append("# HELP app_uptime_seconds Time the application has been running")
        lines.append("# TYPE app_uptime_seconds gauge")
        lines.append(f'app_uptime_seconds {time.time() - self._start_time:.1f}')

        with self._lock:
            # Counters
            for name, value in sorted(self._counters.items()):
                lines.append(f"# TYPE {name} counter")
                lines.append(f"{name} {value}")

            # Gauges
            for name, value in sorted(self._gauges.items()):
                lines.append(f"# TYPE {name} gauge")
                lines.append(f"{name} {value:.2f}")

            # Histograms (summary stats)
            for name, values in sorted(self._histograms.items()):
                if not values:
                    continue
                lines.append(f"# HELP {name} Histogram of {name}")
                lines.append(f"# TYPE {name} summary")
                sorted_vals = sorted(values)
                n = len(sorted_vals)
                lines.append(f'{name}{{quantile="0.5"}} {sorted_vals[n//2]:.2f}')
                lines.append(f'{name}{{quantile="0.9"}} {sorted_vals[int(n*0.9)]:.2f}')
                lines.append(f'{name}{{quantile="0.99"}} {sorted_vals[int(n*0.99)]:.2f}')
                lines.append(f'{name}_sum {sum(sorted_vals):.2f}')
                lines.append(f'{name}_count {n}')

        return "\n".join(lines) + "\n"

    def to_dict(self) -> dict:
        """Export metrics as a dictionary."""
        with self._lock:
            summary = {}
            for name, values in self._histograms.items():
                if values:
                    sorted_vals = sorted(values)
                    n = len(sorted_vals)
                    summary[name] = {
                        "count": n,
                        "mean": sum(sorted_vals) / n,
                        "p50": sorted_vals[n // 2],
                        "p90": sorted_vals[int(n * 0.9)],
                        "p99": sorted_vals[int(n * 0.99)],
                    }
            return {
                "uptime_seconds": time.time() - self._start_time,
                "counters": dict(self._counters),
                "gauges": dict(self._gauges),
                "histograms": summary,
            }


# Global singleton
_collector = MetricsCollector()


def get_metrics_collector() -> MetricsCollector:
    return _collector


# ============================================================
# Predefined metric helpers
# ============================================================

def record_query(duration_ms: float, token_usage: int, success: bool, source: str = "api"):
    """Record metrics for a query."""
    _collector.inc("queries_total")
    if success:
        _collector.inc("queries_success_total")
    else:
        _collector.inc("queries_error_total")
    _collector.observe("query_duration_ms", duration_ms)
    _collector.observe("query_tokens", token_usage)


def record_upload(filename: str, chunks: int, duration_ms: float):
    """Record metrics for a document upload."""
    _collector.inc("uploads_total")
    _collector.observe("upload_duration_ms", duration_ms)
    _collector.set("last_upload_chunks", chunks)


# ============================================================
# Health Check
# ============================================================

def _check_redis() -> dict:
    """Check Redis connectivity.

    Redis is an *optional* dependency: when unavailable the app falls back to
    an in-memory store (see app.memory.memory_manager). Its absence therefore
    means "degraded" operation, not a hard failure.
    """
    try:
        import redis as redis_lib
        import app.core.config as cfg
        r = redis_lib.from_url(cfg.REDIS_URL, socket_timeout=2)
        r.ping()
        return {"status": "healthy", "message": "Connected"}
    except Exception as e:
        return {
            "status": "degraded",
            "message": f"not available ({e}); using in-memory fallback",
        }


def _check_disk() -> dict:
    """Check disk space."""
    try:
        import app.core.config as cfg
        usage = psutil.disk_usage(cfg.UPLOAD_DIR if os.path.exists(cfg.UPLOAD_DIR) else ".")
        free_pct = usage.percent
        return {
            "status": "healthy" if free_pct < 90 else "warning" if free_pct < 95 else "unhealthy",
            "free_percent": round(100 - usage.percent, 1),
            "free_gb": round(usage.free / (1024**3), 2),
        }
    except Exception as e:
        return {"status": "unknown", "message": str(e)}


def _check_memory() -> dict:
    """Check memory usage."""
    try:
        process = psutil.Process()
        mem_mb = process.memory_info().rss / (1024 * 1024)
        system_mem = psutil.virtual_memory()
        return {
            "status": "healthy" if mem_mb < 1024 else "warning",
            "process_mb": round(mem_mb, 1),
            "system_percent_used": system_mem.percent,
        }
    except Exception as e:
        return {"status": "unknown", "message": str(e)}


# ============================================================
# API Endpoints
# ============================================================

@router.get("/metrics", response_class=PlainTextResponse)
def metrics():
    """Prometheus-compatible metrics endpoint."""
    # Update system gauges before export
    try:
        process = psutil.Process()
        _collector.set("process_memory_mb", process.memory_info().rss / (1024 * 1024))
        _collector.set("system_cpu_percent", psutil.cpu_percent(interval=0.1))
        _collector.set("system_memory_percent", psutil.virtual_memory().percent)
    except Exception:
        pass

    return _collector.to_prometheus()


@router.get("/health")
def health():
    """Enhanced health check with subsystem status."""
    checks = {
        "redis": _check_redis(),
        "disk": _check_disk(),
        "memory": _check_memory(),
    }

    # Overall status:
    #   - "unhealthy" only when a critical check hard-fails (e.g. disk full)
    #   - "degraded" when an optional dependency is missing or a soft threshold
    #     is exceeded (redis down, high disk/mem usage). The service is still
    #     serving traffic, so it returns HTTP 200 in degraded mode.
    overall = "healthy"
    for name, check in checks.items():
        if check.get("status") == "unhealthy":
            overall = "unhealthy"
            break
        elif check.get("status") in ("degraded", "warning"):
            overall = "degraded"

    status_code = 200 if overall in ("healthy", "degraded") else 503

    return JSONResponse(
        status_code=status_code,
        content={
            "status": overall,
            "version": "1.0.0",
            "timestamp": datetime.now().isoformat(),
            "uptime_seconds": time.time() - _collector._start_time,
            "checks": checks,
        },
    )


@router.get("/stats")
def stats():
    """Application statistics endpoint."""
    metrics_data = _collector.to_dict()

    # Add trace store stats if available
    try:
        from app.observability.tracker import get_trace_store
        trace_store = get_trace_store()
        metrics_data["traces"] = trace_store.summary()
    except Exception:
        pass

    return metrics_data