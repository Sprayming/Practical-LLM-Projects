from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
import time
from loguru import logger
from app.monitoring.metrics import record_request


class MonitoringMiddleware(BaseHTTPMiddleware):
    """监控中间件 - 自动记录请求指标"""
    
    async def dispatch(self, request: Request, call_next):
        # 跳过监控端点本身，避免递归
        if request.url.path.startswith("/api/monitoring/"):
            return await call_next(request)
        
        start_time = time.perf_counter()
        
        # 记录请求开始
        method = request.method
        endpoint = request.url.path
        
        try:
            response = await call_next(request)
            
            # 计算延迟
            latency = time.perf_counter() - start_time
            
            # 记录指标
            record_request(
                method=method,
                endpoint=endpoint,
                status_code=response.status_code,
                latency=latency
            )
            
            # 添加响应头
            response.headers["X-Process-Time"] = f"{latency:.4f}"
            
            return response
            
        except Exception as e:
            # 记录错误请求
            latency = time.perf_counter() - start_time
            record_request(
                method=method,
                endpoint=endpoint,
                status_code=500,
                latency=latency
            )
            raise


class SlowRequestMiddleware(BaseHTTPMiddleware):
    """慢请求日志中间件"""
    
    def __init__(self, app, slow_threshold: float = 2.0):
        super().__init__(app)
        self.slow_threshold = slow_threshold
    
    async def dispatch(self, request: Request, call_next):
        start_time = time.perf_counter()
        
        response = await call_next(request)
        
        latency = time.perf_counter() - start_time
        
        # 如果请求超过阈值，记录警告
        if latency > self.slow_threshold:
            logger.warning(
                "慢请求: {} {} 耗时 {:.2f}s",
                request.method,
                request.url.path,
                latency
            )
        
        return response