import os
os.environ['TRANSFORMERS_OFFLINE'] = '1'
os.environ['HF_HUB_DISABLE_SYMLINKS_WARNING'] = '1'
os.environ['CURL_CA_BUNDLE'] = ''
os.environ['REQUESTS_CA_BUNDLE'] = ''
# os.environ['HF_ENDPOINT'] = ''
import os
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
import uvicorn

env_path = Path(__file__).resolve().parent.parent / ".env"
if env_path.exists():
    load_dotenv(str(env_path))

from app.api.auth import router as auth_router
from app.api.chat import router as chat_router
from app.api.documents import router as documents_router
from app.api.feedback import router as feedback_router
from app.api.admin import router as admin_router
from app.api.category import router as category_router
from app.api.conversation import router as conversation_router
from app.api.ab_testing import router as ab_testing_router
from app.api.webhook import router as webhook_router
from app.security.middleware import (
    SecurityHeadersMiddleware,
    RequestSizeLimitMiddleware,
)
from app.security.error_handlers import setup_error_handlers
from app.observability.monitoring import router as monitoring_router

app = FastAPI(
    title="Legal Document RAG API",
    version="1.0.0",
    docs_url="/docs" if os.getenv("ENV") != "production" else None,
    redoc_url="/redoc" if os.getenv("ENV") != "production" else None,
)

# Setup global error handlers
setup_error_handlers(app)

# CORS - restrict origins in production
allowed_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

# Security headers
app.add_middleware(SecurityHeadersMiddleware)

# Request size limit (100MB for document uploads)
app.add_middleware(RequestSizeLimitMiddleware, max_size_mb=100)

app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(documents_router)
app.include_router(feedback_router)
app.include_router(admin_router)  # 管理员后台API
app.include_router(category_router)  # 文档分类API
app.include_router(conversation_router)  # 对话管理API
app.include_router(ab_testing_router)  # A/B测试API
app.include_router(webhook_router)  # Webhook通知API
app.include_router(monitoring_router)  # /health, /metrics, /stats

frontend_dir = Path(__file__).resolve().parent / "frontend"

@app.get("/", response_class=HTMLResponse)
async def root():
    html = frontend_dir / "index.html"
    if html.exists():
        return HTMLResponse(content=html.read_bytes(), media_type="text/html; charset=utf-8")
    return Response(content="<h1>Frontend not found</h1>", media_type="text/html")
frontend_dir.mkdir(exist_ok=True)
app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")

# Start webhook manager on app startup
@app.on_event("startup")
async def startup_event():
    from app.worker.webhook import get_webhook_manager
    webhook_manager = get_webhook_manager()
    webhook_manager.start()

@app.on_event("shutdown")
async def shutdown_event():
    from app.worker.webhook import get_webhook_manager
    webhook_manager = get_webhook_manager()
    webhook_manager.stop()

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
