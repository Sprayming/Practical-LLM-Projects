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

from teaching.models import ChatRequest, ChatResponse
from teaching.retrieval.retriever import get_retriever      # 检索器
from teaching.generation.llm import get_llm                 # LLM 服务

router = APIRouter(prefix="/api/chat", tags=["Chat"])


@router.post("/", response_model=ChatResponse)
async def ask(req: ChatRequest):
    """POST /api/chat/ — 提问并获取回答。
    
    完整流程：
    1. 用检索器搜相关文本块
    2. 如果没找到，返回"无法回答"
    3. 如果有相关文本，传给 DeepSeek 生成回答
    4. 返回回答 + 引用来源 + 统计数据
    """
    start = time.perf_counter()  # 计时开始
    
    try:
        # ── 第1步：检索 ──
        retriever = get_retriever()
        sources = retriever.retrieve(
            query=req.query,
            top_k=req.top_k,
            document_ids=req.document_ids,
        )

        # ── 如果没有找到相关资料 ──
        if not sources:
            elapsed = (time.perf_counter() - start) * 1000
            return ChatResponse(
                answer="未找到相关参考资料，无法回答该问题。请上传相关文档后再试。",
                sources=[],
                latency_ms=round(elapsed, 1),
                tokens_used=0,
            )

        # ── 第2步：生成回答 ──
        llm = get_llm()
        answer, tokens = llm.generate(req.query, sources)
        elapsed = (time.perf_counter() - start) * 1000

        return ChatResponse(
            answer=answer,
            sources=sources,
            latency_ms=round(elapsed, 1),
            tokens_used=tokens,
        )
    
    except Exception as e:
        logger.error("Chat failed: {}", e)
        raise HTTPException(status_code=500, detail=f"问答生成失败: {e}")
