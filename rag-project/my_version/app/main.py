# ============================================================
# FastAPI 应用入口 — 整个项目的启动点
#
# 职责：
#   1. 创建 FastAPI 应用实例
#   2. 配置 CORS（让前端可以跨域访问）
#   3. 注册所有路由
#   4. 启动时初始化 ChromaDB
#   5. 全局异常处理
# ============================================================

from __future__ import annotations

from contextlib import asynccontextmanager  # 管理应用生命周期

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware  # 跨域中间件
from fastapi.responses import JSONResponse
from loguru import logger

from app.config import settings
from app.models import ErrorResponse, HealthResponse
from app.retrieval.vector_store import get_vector_store
from app.api import documents, chat  # 导入路由模块



@asynccontextmanager# 管理应用生命周期
async def lifespan(app: FastAPI):
    """应用生命周期。
    yield 前是应用启动时，yield 后是应用关闭时。
    """
    
    logger.info("RAG Enterprise Knowledge Base API is starting...")
    try:
        store = get_vector_store()
        logger.info("Vector store is ready:{}chunks",store.count)
    except Exception as e:
        logger.error("Failed to initialize vector store: {}", e)
    yield
    logger.info("RAG Enterprise Knowledge Base API is shutting down...")





# 创建fastAPI应用实例
app = FastAPI(
    title="RAG Enterprise Knowledge Base API",
    version="0.1.0",
    lifespan=lifespan)# 配置应用生命周期

# 引入CORS,配置跨域
app.add_middleware(
    CORSMiddleware,  # 允许前端页面访问后端API
    allow_origins=["*"],  # 允许所有的来源，不管访问者是本地服务器还是网络服务器（百度）
    allow_credentials=True,  # 允许携带cookie，默认为false，因为前端可能会带上 cookie
    allow_methods=["*"],  # 允许所有的请求方法，不管是GET POST PUT DELETE都可以支持
    allow_headers=["*"],  # 允许所有的请求头，任何请求头都可以支持
)

# 注册路由
app.include_router(documents.router)
app.include_router(chat.router)

# 全局异常处理
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """全局异常处理函数。
    所有未捕获的异常都会被这个函数捕获。
    """
    logger.error("Exception occurred: {}", exc)
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            detail=str(exc),code="INTERVAL_ERROR").model_dump(),
    )   

# 健康检查
@app.get("/health", response_model=HealthResponse)
async def health_check():
    """GET /api/health — 检查服务是否正常。"""
    try:
        stats= get_vector_store().health()
    except Exception :
        stats = None
    return HealthResponse(
        status="OK",
        api_key_configured = settings.api_key is not None,
        collection_stats=stats,
    )

# 启动应用
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)