"""
RideOps AI — 网约车运营数据分析助手
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from pathlib import Path
from app.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("RideOps AI 启动中 ...")
    # 确保目录存在
    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
    Path("reports/output").mkdir(parents=True, exist_ok=True)
    yield
    print("RideOps AI 已关闭")


app = FastAPI(title="RideOps AI", description="网约车运营数据分析 AI 助手", version="0.1.0", lifespan=lifespan)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# 注册路由
from app.api import data, analysis, reports
app.include_router(data.router)
app.include_router(analysis.router)
app.include_router(reports.router)


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "0.1.0", "api_key_configured": bool(settings.llm_api_key)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
