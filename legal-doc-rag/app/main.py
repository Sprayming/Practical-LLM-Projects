"""
main —— legal-doc-rag FastAPI 应用入口模块

【作用与功能】
该模块是 legal-doc-rag RAG 系统的 Web 服务统一入口，负责创建并配置 FastAPI
应用实例：加载环境变量、装配 CORS 与安全中间件、注册全局限流与错误处理器、
挂载所有业务路由（鉴权、对话、文档、反馈、管理后台、分类、会话、A/B 测试、
Webhook、监控），并提供前端静态资源服务。同时定义了应用启动/关闭钩子，
在启动时恢复未完成文档索引任务、启动 Webhook 管理器。

【主要组成】
- `app`：全局 FastAPI 实例。
- `root()`：根路径处理器，返回前端入口 HTML。
- `startup_event()`：启动钩子，启动后台服务并恢复未完成的索引任务。
- `_recover_incomplete_indexing()`：扫描上传目录，对未索引的 PDF 重新提交任务。
- `shutdown_event()`：关闭钩子，优雅停止 Webhook 管理器。

【适用场景】
- 场景1：以 `python -m app.main` 或 uvicorn 直接启动 ASGI 服务。
- 场景2：被容器/进程管理器（如 gunicorn + uvicorn worker）加载 `app.main:app`。

【依赖关系】
- 上游调用方：ASGI 服务器（uvicorn）、容器编排。
- 下游依赖：app.api.* 各路由、app.security.*、app.worker.webhook、
  app.core.limiter、app.core.config 等子模块。
"""

import os

# 设置环境变量，强制 Transformers 库在离线模式下运行，避免联网检查模型更新
os.environ['TRANSFORMERS_OFFLINE'] = '1'
# 禁用 HuggingFace Hub 关于符号链接的警告信息
os.environ['HF_HUB_DISABLE_SYMLINKS_WARNING'] = '1'
# os.environ['HF_ENDPOINT'] = '' # 可选：配置自定义的 HuggingFace 镜像端点

import os
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
import uvicorn

# 尝试加载项目根目录下的 .env 环境变量配置文件
env_path = Path(__file__).resolve().parent.parent / ".env"
if env_path.exists():
    load_dotenv(str(env_path))

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

# 导入安全相关中间件和全局错误处理器
from app.security.middleware import (
    SecurityHeadersMiddleware,
    RequestSizeLimitMiddleware,
)
from app.security.error_handlers import setup_error_handlers
from app.observability.monitoring import router as monitoring_router

# 初始化 FastAPI 应用实例，配置 API 文档信息
app = FastAPI(
    title="Legal Document RAG API",
    version="1.0.0",
    # 在生产环境中关闭 Swagger UI 和 ReDoc 文档接口，提高安全性
    docs_url="/docs" if os.getenv("ENV") != "production" else None,
    redoc_url="/redoc" if os.getenv("ENV") != "production" else None,
)

# 设置全局错误处理器，统一异常返回格式
setup_error_handlers(app)

# 配置接口速率限制
from app.core.limiter import limiter
from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler
# 将限流器实例绑定到 app.state，并注册触发限流时的异常处理回调
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# 配置 CORS (跨域资源共享) - 在生产环境中应严格限制允许的源
allowed_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

# 添加安全响应头中间件（如 X-Content-Type-Options, X-Frame-Options 等）
app.add_middleware(SecurityHeadersMiddleware)

# 添加请求体大小限制中间件（限制为 100MB，主要用于文档上传场景）
app.add_middleware(RequestSizeLimitMiddleware, max_size_mb=100)

# 注册所有业务路由
app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(documents_router)
app.include_router(feedback_router)
app.include_router(admin_router)        # 管理员后台API
app.include_router(category_router)     # 文档分类API
app.include_router(conversation_router) # 对话管理API
app.include_router(ab_testing_router)   # A/B测试API
app.include_router(webhook_router)      # Webhook通知API
app.include_router(monitoring_router)   # 监控探针与指标API (/health, /metrics, /stats)

# 指定前端静态文件所在的目录
frontend_dir = Path(__file__).resolve().parent / "frontend"

@app.get("/", response_class=HTMLResponse)
async def root():
    """
    根路径处理函数，返回前端单页应用的入口 HTML。
    
    如果在前端目录下找到 index.html，则返回其内容；否则返回未找到的提示。
    """
    html = frontend_dir / "index.html"
    if html.exists():
        return HTMLResponse(content=html.read_bytes(), media_type="text/html; charset=utf-8")
    return Response(content="<h1>Frontend not found</h1>", media_type="text/html")

# 确保前端目录存在，并将该目录挂载到根路径以提供静态资源服务 (JS/CSS/图片等)
frontend_dir.mkdir(exist_ok=True)
app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")


@app.on_event("startup")
async def startup_event():
    """
    应用启动事件钩子。
    
    在 FastAPI 应用启动时执行：
    1. 启动 Webhook 管理器，开始监听并处理外部通知。
    2. 调用恢复函数，检查并重新提交因服务异常中断而未完成的文档索引任务。
    """
    from app.worker.webhook import get_webhook_manager
    webhook_manager = get_webhook_manager()
    webhook_manager.start()
    # 执行未完成索引任务的恢复逻辑
    _recover_incomplete_indexing()


def _recover_incomplete_indexing():
    """
    启动时扫描上传目录，对尚未完成向量化的文档自动重新提交索引任务。
    
    该函数用于处理服务意外重启或崩溃后的数据一致性问题。
    它会遍历所有租户的上传目录，比对向量数据库中已存在的记录，
    找出遗漏的 PDF 文件并重新创建索引任务提交到后台 Worker 执行。
    
    工作流程：
    1. 遍历上传目录下的各个租户文件夹。
    2. 提取该租户文件夹下所有的 PDF 文件名。
    3. 检查向量数据库，获取已成功索引的文件来源列表。
    4. 检查任务队列，获取当前正在处理或等待中的文件列表，防止重复提交。
    5. 对于既不在向量库也不在活动任务中的文件，创建新的索引任务并提交。
    """
    import os
    from app.core import config as cfg
    from app.tasks.task_store import (
        create_task,
        submit_indexing_job,
        list_tasks_for_tenant,
    )
    from app.api.documents import _run_indexing
    from langchain_community.vectorstores import Chroma
    from app.retrieval.embedder_factory import create_embedder

    # 如果全局上传目录不存在，直接返回
    if not os.path.exists(cfg.UPLOAD_DIR):
        return

    # 延迟初始化 embedder，避免在不需要恢复时占用资源
    embedder = None

    # 遍历上传目录下的所有项（预期为租户ID文件夹）
    for tenant_id in os.listdir(cfg.UPLOAD_DIR):
        tenant_upload_dir = os.path.join(cfg.UPLOAD_DIR, tenant_id)
        
        # 跳过非目录文件
        if not os.path.isdir(tenant_upload_dir):
            continue

        # 获取当前租户目录下所有的 PDF 文件
        pdfs = [f for f in os.listdir(tenant_upload_dir) if f.lower().endswith(".pdf")]
        if not pdfs:
            continue

        # 检查向量库中已有的文档记录，避免重复索引
        persist_dir = os.path.join(cfg.CHROMA_PERSIST_DIR, tenant_id)
        existing_sources = set()
        if os.path.exists(persist_dir):
            try:
                # 懒加载：仅在确认有向量库目录时才初始化 embedder
                if embedder is None:
                    embedder = create_embedder()
                store = Chroma(
                    embedding_function=embedder,
                    persist_directory=persist_dir,
                )
                # 从 Chroma 底层 collection 获取元数据，提取 source 字段
                metas = store._collection.get(include=["metadatas"]).get("metadatas") or []
                existing_sources = {m.get("source") for m in metas if m.get("source")}
            except Exception:
                # 如果读取向量库发生异常，视作没有已存在记录，后续会尝试重新索引
                existing_sources = set()

        # 检查任务队列，避免与已有未完成任务重复提交
        active_files = {
            t["filename"]
            for t in list_tasks_for_tenant(tenant_id)
            if t["status"] in ("pending", "processing")
        }

        # 遍历所有 PDF 文件，提交缺失的索引任务
        for filename in pdfs:
            # 如果文件已成功索引，或正在索引中，则跳过
            if filename in existing_sources:
                continue
            if filename in active_files:
                continue
            
            # 符合条件：文件存在但未被索引且无活动任务，重新提交索引
            file_path = os.path.join(tenant_upload_dir, filename)
            task_id = create_task(tenant_id, filename)
            submit_indexing_job(_run_indexing, task_id, tenant_id, file_path, filename)


@app.on_event("shutdown")
async def shutdown_event():
    """
    应用关闭事件钩子。
    
    在 FastAPI 应用正常关闭时执行，用于优雅地停止 Webhook 管理器等后台服务，
    释放相关资源，避免资源泄漏或数据丢失。
    """
    from app.worker.webhook import get_webhook_manager
    webhook_manager = get_webhook_manager()
    webhook_manager.stop()

# 当脚本直接运行时，使用 uvicorn 启动 ASGI 服务
if __name__ == "__main__":
    # host="0.0.0.0" 允许外部网络访问，端口设为 8000，开启热重载便于开发调试
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
