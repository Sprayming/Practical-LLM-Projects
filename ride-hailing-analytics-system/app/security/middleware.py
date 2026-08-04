from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
import re
import time
from loguru import logger


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """安全头中间件"""
    
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        
        # 添加安全头
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = "default-src 'self'"
        
        return response


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """请求大小限制中间件"""
    
    def __init__(self, app, max_size: int = 1024 * 1024):  # 1MB
        super().__init__(app)
        self.max_size = max_size
    
    async def dispatch(self, request: Request, call_next):
        # 检查内容长度
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > self.max_size:
            return JSONResponse(
                status_code=413,
                content={"detail": "请求体过大"}
            )
        
        return await call_next(request)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """速率限制中间件"""
    
    def __init__(self, app, requests_per_minute: int = 60):
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.requests = {}  # IP -> [timestamp, ...]
    
    async def dispatch(self, request: Request, call_next):
        client_ip = request.client.host
        current_time = time.time()
        
        # 清理过期记录
        if client_ip in self.requests:
            self.requests[client_ip] = [
                t for t in self.requests[client_ip]
                if current_time - t < 60
            ]
        else:
            self.requests[client_ip] = []
        
        # 检查速率限制
        if len(self.requests[client_ip]) >= self.requests_per_minute:
            return JSONResponse(
                status_code=429,
                content={"detail": "请求过于频繁，请稍后再试"}
            )
        
        # 记录请求
        self.requests[client_ip].append(current_time)
        
        return await call_next(request)


class SQLInjectionMiddleware(BaseHTTPMiddleware):
    """SQL注入检测中间件"""
    
    DANGEROUS_PATTERNS = [
        r";\s*(DROP|ALTER|TRUNCATE|CREATE)\s+",
        r"UNION\s+ALL\s+SELECT",
        r"INTO\s+(OUTFILE|DUMPFILE)",
        r"LOAD_FILE\s*\(",
        r"BENCHMARK\s*\(",
        r"SLEEP\s*\(",
        r"WAITFOR\s+DELAY",
    ]
    
    async def dispatch(self, request: Request, call_next):
        # 只检查POST请求的JSON体
        if request.method == "POST" and request.headers.get("content-type") == "application/json":
            try:
                body = await request.body()
                body_str = body.decode("utf-8")
                
                # 检查危险模式
                for pattern in self.DANGEROUS_PATTERNS:
                    if re.search(pattern, body_str, re.IGNORECASE):
                        logger.warning("检测到潜在SQL注入: {}", body_str[:200])
                        return JSONResponse(
                            status_code=400,
                            content={"detail": "检测到潜在的恶意请求"}
                        )
            except Exception:
                pass
        
        return await call_next(request)