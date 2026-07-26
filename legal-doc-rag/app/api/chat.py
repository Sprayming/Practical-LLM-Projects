import os, sys, json, requests
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel
from typing import List, Optional
from app.retrieval.embedder_factory import create_embedder
from langchain_community.vectorstores import Chroma
import app.core.config as cfg
from app.api.auth import get_user_from_token

router = APIRouter(prefix="/api/chat", tags=["chat"])

class ChatRequest(BaseModel):
    message: str
    history: Optional[List[dict]] = []

class Message(BaseModel):
    role: str
    content: str

def _require_user(authorization: str = Header(...)) -> dict:
    token = authorization.replace("Bearer ", "").strip()
    if not token:
        raise HTTPException(401, "Missing token")
    return get_user_from_token(token)

@router.post("")
def chat(req: ChatRequest, user: dict = Depends(_require_user)):
    tenant_id = user["tenant_id"]
    persist_dir = os.path.join(cfg.CHROMA_PERSIST_DIR, tenant_id)

    if not os.path.exists(persist_dir):
        return {"answer": "请先上传文档", "citations": [], "token_usage": 0}

    embedder = create_embedder()
    try:
        vector_store = Chroma(
            embedding_function=embedder,
            persist_directory=persist_dir,
        )
        docs = vector_store.similarity_search(req.message, k=3)
    except Exception:
        return {"answer": "向量库加载失败，请重新上传文档", "citations": [], "token_usage": 0}

    context = "\n\n".join([f"[chunk {d.metadata.get('chunk', 0)+1}] {d.page_content}" for d in docs])

    history_text = ""
    for m in (req.history or [])[-4:]:
        history_text += f"{m.get('role', 'user')}: {m.get('content', '')[:200]} " + chr(10)

    prompt = f"""You are a legal expert assistant. Answer based on the provided text.

Reference text:
{context}

Question: {req.message}

Requirements: Cite relevant chunks using [chunk N] notation. If the text doesn't contain the answer, state that clearly."""

    try:
        resp = requests.post(
            f"{cfg.LLM_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {cfg.LLM_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": cfg.LLM_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
                "max_tokens": 1024,
            },
            timeout=60,
            verify=False,
        )
        if resp.status_code != 200:
            return {"answer": f"API错误: {resp.status_code}", "citations": [], "token_usage": 0}
        data = resp.json()
        answer = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        token_usage = usage.get("total_tokens", 0)
    except Exception as e:
        return {"answer": f"LLM调用??: {str(e)}", "citations": [], "token_usage": 0}

    citations = [
        {"source": d.metadata.get("source", ""), "content": d.page_content[:200]}
        for d in docs
    ]

    return {"answer": answer, "citations": citations, "token_usage": token_usage}
