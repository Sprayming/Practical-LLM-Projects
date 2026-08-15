"""
app/main/routes.py —— 路由注册模块

【作用与功能】
负责注册所有业务路由。
"""

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, Response
from pathlib import Path

# 导入各个业务模块的 API 路由器
from app.api.auth import router as auth_router
from app.api.chat import router as chat_router
from app.api.documents import router as documents_router
from app.api.feedback import router as feedback_router
from app.api.admin import router as admin_router
from app.api.category import router as category_router
from app.api.conversation import router as conversation_router
from app.api.ab_testing import router as ab_testing_router
from app.api.webhook import router as webhook_router
from app.observability.monitoring import router as monitoring_router

def setup_routes(app: FastAPI):
    """
    注册所有业务路由
    
    Args:
        app (FastAPI): FastAPI 应用实例
    """
    # 注册所有业务路由
    app.include_router(auth_router)
    app.include_router(chat_router)
    app.include_router(documents_router)
    app.include_router(feedback_router)
    app.include_router(admin_router)
    app.include_router(category_router)
    app.include_router(conversation_router)
    app.include_router(ab_testing_router)
    app.include_router(webhook_router)
    app.include_router(monitoring_router)

def setup_static_files(app: FastAPI):
    """
    配置静态文件服务
    
    Args:
        app (FastAPI): FastAPI 应用实例
    """
    # 本文件位于 app/main/ 包内，__file__.parent 是 app/main；
    # 而前端目录实际在 app/frontend，需向上一级再拼接。
    frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
    frontend_dir.mkdir(exist_ok=True)

    @app.get("/", response_class=HTMLResponse)
    async def root():
        """
        根路径处理函数，返回前端单页应用的入口 HTML。
        """
        html = frontend_dir / "index.html"
        if html.exists():
            return HTMLResponse(content=html.read_bytes(), media_type="text/html; charset=utf-8")
        return Response(content="<h1>Frontend not found</h1>", media_type="text/html")

    # 挂载静态文件
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
