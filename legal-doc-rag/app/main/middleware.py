"""
app/main/middleware.py —— 中间件配置模块

【作用与功能】
负责配置所有中间件。
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.security.middleware import SecurityHeadersMiddleware, RequestSizeLimitMiddleware
from app.main.config import ALLOWED_ORIGINS
from app.core.limiter import limiter
from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler

def setup_middleware(app: FastAPI):
    """
    设置所有中间件
    
    Args:
        app (FastAPI): FastAPI 应用实例
    """
    # 配置 CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )

    # 添加安全响应头中间件
    app.add_middleware(SecurityHeadersMiddleware)

    # 添加请求体大小限制中间件
    app.add_middleware(RequestSizeLimitMiddleware, max_size_mb=100)

    # 配置接口速率限制
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
