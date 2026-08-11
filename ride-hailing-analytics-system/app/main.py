from __future__ import annotations
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.api import query, dashboard
from app.security.middleware import (
    SecurityHeadersMiddleware,
    RequestSizeLimitMiddleware,
    RateLimitMiddleware,
    SQLInjectionMiddleware
)
from app.security.error_handlers import register_error_handlers
from app.monitoring.metrics import router as monitoring_router
from app.monitoring.middleware import MonitoringMiddleware, SlowRequestMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时执行
    from app.db.connection import init_db
    init_db()
    from loguru import logger
    logger.info("应用启动完成")
    yield
    # 关闭时执行
    from loguru import logger
    logger.info("应用关闭")


app = FastAPI(
    title="Ride-Hailing Analytics System",
    version="0.5.0",
    description="基于多Agent协作的网约车智能数据分析系统",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

# 注册错误处理器
register_error_handlers(app)

# 添加监控中间件（最外层）
app.add_middleware(MonitoringMiddleware)
app.add_middleware(SlowRequestMiddleware, slow_threshold=2.0)

# 添加安全中间件
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestSizeLimitMiddleware, max_size=1024 * 1024)  # 1MB
app.add_middleware(RateLimitMiddleware, requests_per_minute=60)
app.add_middleware(SQLInjectionMiddleware)

# 添加CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应限制具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(query.router)
app.include_router(dashboard.router)
app.include_router(monitoring_router)

# 查询历史路由（可选，根据需求启用）
try:
    from app.api import history
    app.include_router(history.router)
except ImportError:
    pass

# 任务路由（可选，根据需求启用）
try:
    from app.api import tasks
    app.include_router(tasks.router)
except ImportError:
    pass

# 认证路由（可选，根据需求启用）
try:
    from app.api import auth
    app.include_router(auth.router)
except ImportError:
    pass

# 报告路由（可选，根据需求启用）
try:
    from app.api import report
    app.include_router(report.router)
except ImportError:
    pass

# 异常检测路由（可选，根据需求启用）
try:
    from app.api import anomaly
    app.include_router(anomaly.router)
except ImportError:
    pass

# 静态文件服务
from fastapi.staticfiles import StaticFiles
import os

static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/", tags=["Root"])
async def root():
    """根端点 - 问答聊天首页"""
    from fastapi.responses import FileResponse

    static_file = os.path.join(os.path.dirname(__file__), "static", "chat.html")
    if os.path.exists(static_file):
        return FileResponse(static_file)

    return {
        "message": "Ride-Hailing Analytics System API",
        "version": "0.1.0",
        "docs": "/docs",
    }


@app.get("/dashboard", tags=["Root"])
async def dashboard_page():
    """数据分析仪表盘（次级页）"""
    from fastapi.responses import FileResponse

    static_file = os.path.join(os.path.dirname(__file__), "static", "index.html")
    if os.path.exists(static_file):
        return FileResponse(static_file)

    return {"message": "index.html not found"}


@app.get("/apiview", tags=["Root"])
async def api_view():
    """离线版 API 文档（不依赖外网 CDN，WorkBuddy 预览面板可用）"""
    from fastapi.responses import FileResponse
    f = os.path.join(os.path.dirname(__file__), "static", "apidocs.html")
    if os.path.exists(f):
        return FileResponse(f)
    return {"message": "apidocs.html not found"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8001, reload=True)
