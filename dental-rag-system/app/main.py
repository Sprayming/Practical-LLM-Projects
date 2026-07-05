# ============================================================
# FastAPI 搴旂敤鍏ュ彛 鈥?鏁翠釜椤圭洰鐨勫惎鍔ㄧ偣
#
# 鑱岃矗锛?#   1. 鍒涘缓 FastAPI 搴旂敤瀹炰緥
#   2. 閰嶇疆 CORS锛堣鍓嶇鍙互璺ㄥ煙璁块棶锛?#   3. 娉ㄥ唽鎵€鏈夎矾鐢?#   4. 鍚姩鏃跺垵濮嬪寲 ChromaDB
#   5. 鍏ㄥ眬寮傚父澶勭悊
# ============================================================

from __future__ import annotations

from contextlib import asynccontextmanager  # 绠＄悊搴旂敤鐢熷懡鍛ㄦ湡

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware  # 璺ㄥ煙涓棿浠?from fastapi.responses import JSONResponse
from loguru import logger

from app.config import settings
from app.models import ErrorResponseModel, HealthResponseModel
from app.retrieval.vector_store import get_vector_store
from app.api import documents, chat  # 瀵煎叆璺敱妯″潡



@asynccontextmanager# 绠＄悊搴旂敤鐢熷懡鍛ㄦ湡
async def lifespan(app: FastAPI):
    """搴旂敤鐢熷懡鍛ㄦ湡銆?    yield 鍓嶆槸搴旂敤鍚姩鏃讹紝yield 鍚庢槸搴旂敤鍏抽棴鏃躲€?    """
    
    logger.info("RAG Enterprise Knowledge Base API is starting...")
    try:
        store = get_vector_store()
        logger.info("Vector store is ready:{}chunks",store.count)
    except Exception as e:
        logger.error("Failed to initialize vector store: {}", e)
    yield
    logger.info("RAG Enterprise Knowledge Base API is shutting down...")





# 鍒涘缓fastAPI搴旂敤瀹炰緥
app = FastAPI(
    title="RAG Enterprise Knowledge Base API",
    version="0.1.0",
    lifespan=lifespan)# 閰嶇疆搴旂敤鐢熷懡鍛ㄦ湡

# 寮曞叆CORS,閰嶇疆璺ㄥ煙
app.add_middleware(
    CORSMiddleware,  # 鍏佽鍓嶇椤甸潰璁块棶鍚庣API
    allow_origins=["*"],  # 鍏佽鎵€鏈夌殑鏉ユ簮锛屼笉绠¤闂€呮槸鏈湴鏈嶅姟鍣ㄨ繕鏄綉缁滄湇鍔″櫒锛堢櫨搴︼級
    allow_credentials=True,  # 鍏佽鎼哄甫cookie锛岄粯璁や负false锛屽洜涓哄墠绔彲鑳戒細甯︿笂 cookie
    allow_methods=["*"],  # 鍏佽鎵€鏈夌殑璇锋眰鏂规硶锛屼笉绠℃槸GET POST PUT DELETE閮藉彲浠ユ敮鎸?    allow_headers=["*"],  # 鍏佽鎵€鏈夌殑璇锋眰澶达紝浠讳綍璇锋眰澶撮兘鍙互鏀寔
)

# 娉ㄥ唽璺敱
app.include_router(documents.router)
app.include_router(chat.router)

# 鍏ㄥ眬寮傚父澶勭悊
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """鍏ㄥ眬寮傚父澶勭悊鍑芥暟銆?    鎵€鏈夋湭鎹曡幏鐨勫紓甯搁兘浼氳杩欎釜鍑芥暟鎹曡幏銆?    """
    logger.error("Exception occurred: {}", exc)
    return JSONResponse(
        status_code=500,
        content=ErrorResponseModel(
            detail=str(exc),code="INTERVAL_ERROR").model_dump(),
    )   

# health check
@app.get("/health", response_model=HealthResponseModel)
async def health_check():
    """Health check endpoint."""
    try:
        stats= get_vector_store().health()
    except Exception :
        stats = None
    return HealthResponseModel(
        status="OK",
        api_key_configured = settings.llm_api_key is not None,
        collection_stats=stats,
    )

# 鍚姩搴旂敤
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
