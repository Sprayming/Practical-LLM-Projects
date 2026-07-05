# ============================================================
# 问答 API — 用户提问 → 检索 → DeepSeek 生成 → 返回
#
# 这就是 RAG 的核心流程：
#   问题 → 向量化 → 搜向量库 → 拼 Prompt → DeepSeek 生成 → 带引用回答
# ============================================================
from __future__ import annotations
import time

from fastapi import APIRouter, HTTPException
from loguru import logger

from app.models import ChatRequestModel, ChatResponseModel
from app.retrieval.retriever import get_retriever      # 检索器
from app.generation.llm import get_llm                 # LLM 服务

router = APIRouter(prefix="/api/chat",tags=["Chat"])

@router.post("/", response_model=ChatResponseModel)
async def chat(request: ChatRequestModel):
    """问答 API
    完整流程：
    1. 检索器检索，用检索器相关文本块
    2. 如果没有找到，就返回”没有找到相关内容“
    3. 如果找到，拼接 Prompt,调用 LLM(现行暂用deepseek)生成回答
    4. 返回回答+引用来源+耗时+统计数据
    """
    start = time.perf_counter()# 记录开始时间
    logger.info("收到请求：{request}",request=request)# 记录请求日志

    # 1. 检索器检索，用检索器相关文本块
    try:
        retriever = get_retriever()
        sources = retriever.retrieve(
            query=request.query,
            top_k=request.top_k,
            document_ids=request.document_ids,
        )
        #  如果没有找到，就返回”没有找到相关内容“
        if not sources:
            elapsed = (time.perf_counter() - start)*1000
            return ChatResponseModel(
                answer="没有找到相关内容",
                sources=[],
                elapsed=elapsed,
                latency_ms=round(elapsed, 2),   # 毫秒
                tokens_used=0,                 # 总 token 数
        )
        # 2. 如果找到，拼接 Prompt,调用 LLM(现行暂用deepseek)生成回答
        llm = get_llm()
        answer,tokens = llm.generate(request.query, sources)
        elapsed = (time.perf_counter() - start)*1000
        return ChatResponseModel(
            answer=answer,
            sources=sources,
            elapsed=elapsed,
            latency_ms=round(elapsed, 2),   # 毫秒
            tokens_used=tokens,             # 总 token 数
    )

    except HTTPException:
        raise  # 重新抛出 HTTPException，避免被下面的 Exception 捕获
    except Exception as e:
        logger.error("检索失败：{error}",error=e)
        raise HTTPException(status_code=500, detail="检索失败")

    
