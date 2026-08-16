"""
app/main/app.py —— FastAPI 应用初始化模块

【作用与功能】
负责创建并完整装配 FastAPI 应用实例，按固定顺序挂载全局错误处理器、
中间件、业务路由、前端静态资源与启动/关闭事件钩子，返回可直接交给
uvicorn 运行的完整应用对象。
"""

from fastapi import FastAPI
import os

# 装配所需的各 setup 函数（均位于同包其他模块）
from .config import setup_config
from .middleware import setup_middleware
from .routes import setup_routes, setup_static_files
from .events import setup_events
from app.security.error_handlers import setup_error_handlers

def create_app() -> FastAPI:
    """
    创建并完整装配 FastAPI 应用实例。

    Returns:
        FastAPI: 已注册错误处理器、中间件、路由、静态资源与事件钩子的应用实例
    """
    app = FastAPI(
        title="Legal Document RAG API",
        version="1.0.0",
        docs_url="/docs" if os.getenv("ENV") != "production" else None,
        redoc_url="/redoc" if os.getenv("ENV") != "production" else None,
    )

    # 1) 全局异常处理器：统一错误返回格式
    setup_error_handlers(app)
    # 2) 中间件：限流、CORS、安全响应头、请求体大小限制
    setup_middleware(app)
    # 3) 业务路由：鉴权/对话/文档/反馈/管理/分类/会话/A-B/Webhook/监控/评测看板
    setup_routes(app)
    # 4) 前端静态资源与根路径处理器
    setup_static_files(app)
    # 5) 启动/关闭事件钩子：Webhook 管理器、未完成索引恢复
    setup_events(app)

    return app
