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

from teaching.config import settings
from teaching.models import ErrorResponse, HealthResponse
from teaching.retrieval.vector_store import get_vector_store
from teaching.api import documents, chat  # 导入路由模块


@asynccontextmanager  # 管理应用生命周期
async def lifespan(app: FastAPI):
    """应用生命周期。
    
    yield 之前的代码在启动时运行
    yield 之后的代码在关闭时运行
    """
    logger.info("Starting RAG Enterprise Backend ...")
    try:
        # 启动时初始化向量库
        store = get_vector_store()
        logger.info("Vector store ready: {} chunks", store.count)
    except Exception as e:
        logger.error("Vector store init failed: {}", e)
    yield  # 应用开始接收请求
    logger.info("Shutting down RAG Enterprise Backend ...")


# 创建 FastAPI 应用
app = FastAPI(
    title="RAG Enterprise Knowledge Base API",  # API 文档标题
    version="0.1.0",
    lifespan=lifespan,  # 注册生命周期管理
)

# ── CORS 配置 ──
# 允许前端页面（即使是 file:// 协议）访问后端 API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有来源（生产环境应限制）
    allow_credentials=True,  # 允许携带 Cookie
    allow_methods=["*"],  # 允许所有 HTTP 方法
    allow_headers=["*"],  # 允许所有请求头
)

# ── 注册路由 ──
app.include_router(documents.router)  # /api/documents/*
app.include_router(chat.router)  # /api/chat/*


# ── 全局异常处理 ──
# 任何未捕获的异常都会走这里，返回 500 错误
@app.exception_handler(Exception)  # 全局异常处理
async def global_handler(request: Request, exc: Exception):
    logger.error("Unhandled {}: {}", request.url, exc)
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(detail=str(exc), code="INTERNAL_ERROR").model_dump(),
    )


# ── 健康检查 ──
@app.get("/api/health", response_model=HealthResponse)
async def health():
    """GET /api/health — 检查服务是否正常。"""
    try:
        stats = get_vector_store().health()
    except Exception:
        stats = None
    return HealthResponse(
        status="ok",
        api_key_configured=bool(settings.llm_api_key),
        collection_stats=stats,
    )


# ── 直接运行入口 ──
if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
