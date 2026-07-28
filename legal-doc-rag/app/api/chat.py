import os, sys, json, requests, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from fastapi import APIRouter, HTTPException, Depends, Header
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional
from app.retrieval.embedder_factory import create_embedder
from app.retrieval.hybrid_retriever import HybridRetriever, Reranker
from app.retrieval.query_rewriter import QueryRewriter
from app.retrieval.citation import CitationTracker
from app.retrieval.cache import QueryCache
from app.memory.memory_manager import MemorySystem
from app.worker.shadow_worker import get_worker
from langchain_community.vectorstores import Chroma
import app.core.config as cfg
from app.api.auth import get_user_from_token

router = APIRouter(prefix="/api/chat", tags=["chat"])

class ChatRequest(BaseModel):
    message: str
    history: Optional[List[dict]] = []
    stream: Optional[bool] = False

def _require_user(authorization: str = Header(...)) -> dict:
    token = authorization.replace("Bearer ", "").strip()
    if not token:
        raise HTTPException(401, "Missing token")
    return get_user_from_token(token)


_memory_cache = {}

def _make_llm_func():
    def f(prompt):
        import requests
        try:
            r = requests.post(f"{cfg.LLM_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {cfg.LLM_API_KEY}", "Content-Type": "application/json"},
                json={"model": cfg.LLM_MODEL, "messages": [{"role": "user", "content": prompt}], "temperature": 0.1, "max_tokens": 512},
                timeout=30, verify=False)
            return r.json()["choices"][0]["message"]["content"]
        except:
            return ""
    return f

def _get_memory(tenant_id, embedder):
    global _memory_cache
    if tenant_id not in _memory_cache:
        pd = os.path.join("memory_db", tenant_id)
        _memory_cache[tenant_id] = MemorySystem(embedder=embedder, persist_dir=pd, tenant_id=tenant_id, worker=get_worker())
    return _memory_cache[tenant_id]

_reranker = None
def _get_reranker():
    global _reranker
    if _reranker is None:
        _reranker = Reranker()
    return _reranker

def _build_pipeline(tenant_id: str):
    embedder = create_embedder()
    persist_dir = os.path.join(cfg.CHROMA_PERSIST_DIR, tenant_id)
    if not os.path.exists(persist_dir):
        return None, None, None, None, None
    vector_store = Chroma(embedding_function=embedder, persist_directory=persist_dir)
    query_rewriter = QueryRewriter(api_key=cfg.LLM_API_KEY, base_url=cfg.LLM_BASE_URL)
    cache = QueryCache(cache_dir=os.path.join("cache", tenant_id))
    citation_tracker = CitationTracker()
    return embedder, vector_store, query_rewriter, cache, citation_tracker

@router.post("/stream")
async def chat_stream(req: ChatRequest, user: dict = Depends(_require_user)):
    embedder, vector_store, qr, cache, ct = _build_pipeline(user["tenant_id"])
    llm_func = _make_llm_func()
    mem = _get_memory(user["tenant_id"], embedder) if embedder else None
    if vector_store is None:
        return StreamingResponse(
            iter([f"data: {json.dumps({'type': 'error', 'content': '请先上传文档'})}\n\n"]),
            media_type="text/event-stream"
        )
    queries = qr.rewrite(req.message, num_variants=1) if qr else [req.message]
    query = queries[0] if queries else req.message
    mem_ctx = mem.get_context(query) if mem else ""
    cached = cache.get(query) if cache else None
    if cached:
        content = cached if isinstance(cached, str) else cached.get("answer", str(cached))
        async def _cached():
            yield f"data: {json.dumps({'type': 'token', 'content': content})}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'citations': [], 'token_usage': 0})}\n\n"
        return StreamingResponse(_cached(), media_type="text/event-stream")
    all_texts = []
    try:
        all_data = vector_store._collection.get()
        all_texts = all_data.get("documents", []) or []
    except Exception:
        pass
    retriever = HybridRetriever(embedder, all_texts, k=10)
    docs = retriever.retrieve(query)
    docs = _get_reranker().rerank(query, docs, top_k=5)
    ct.add_sources(docs)
    context = ct.format_context()
    history_text = ""
    for m in (req.history or [])[-4:]:
        history_text += f"{m.get('role', 'user')}: {m.get('content', '')[:200]} " + chr(10)
    prompt = "You are a legal expert assistant. Answer based on the provided text.\n\nReference text:\n" + context + "\n\nMemory context:\n" + mem_ctx + "\n\nConversation history:\n" + history_text + "\n\nQuestion: " + query + "\n\nRequirements: Cite relevant chunks using [N] notation. If the text doesn't contain the answer, state that clearly."
    async def generate():
        full_answer = ""
        try:
            resp = requests.post(
                f"{cfg.LLM_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {cfg.LLM_API_KEY}", "Content-Type": "application/json"},
                json={"model": cfg.LLM_MODEL, "messages": [{"role": "user", "content": prompt}], "stream": True, "temperature": 0.1, "max_tokens": 1024},
                stream=True, timeout=60, verify=False
            )
            for line in resp.iter_lines():
                if line:
                    decoded = line.decode("utf-8")
                    if decoded.startswith("data: "):
                        data_str = decoded[6:]
                        if data_str == "[DONE]": break
                        try:
                            chunk = json.loads(data_str)
                            token = chunk["choices"][0].get("delta", {}).get("content", "")
                            if token:
                                full_answer += token
                                yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"
                        except json.JSONDecodeError:
                            continue
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"
            return
        sources = ct.get_sources()
        citations = []
        for s in sources:
            txt = s.page_content[:200] if hasattr(s, 'page_content') else str(s)[:200]
            src = s.source if hasattr(s, 'source') else ""
            citations.append({"source": src, "content": txt})
        if cache:
            try: cache.set(query, full_answer)
            except: pass
        if mem:
            try:
                mem.add("user", req.message)
                mem.add("assistant", full_answer)
                mem.trigger_background_jobs(llm_func)
            except:
                pass
        yield f"data: {json.dumps({'type': 'done', 'citations': citations, 'token_usage': 0})}\n\n"
    return StreamingResponse(generate(), media_type="text/event-stream")

@router.post("")
def chat(req: ChatRequest, user: dict = Depends(_require_user)):
    embedder, vector_store, qr, cache, ct = _build_pipeline(user["tenant_id"])
    llm_func = _make_llm_func()
    mem = _get_memory(user["tenant_id"], embedder) if embedder else None
    if vector_store is None:
        return {"answer": "请先上传文档", "citations": [], "token_usage": 0}
    queries = qr.rewrite(req.message, num_variants=1) if qr else [req.message]
    query = queries[0] if queries else req.message
    mem_ctx = mem.get_context(query) if mem else ""
    cached = cache.get(query) if cache else None
    if cached:
        content = cached if isinstance(cached, str) else cached.get("answer", str(cached))
        return {"answer": content, "citations": [], "token_usage": 0}
    all_texts = []
    try:
        all_data = vector_store._collection.get()
        all_texts = all_data.get("documents", []) or []
    except Exception:
        pass
    retriever = HybridRetriever(embedder, all_texts, k=10)
    docs = retriever.retrieve(query)
    docs = _get_reranker().rerank(query, docs, top_k=5)
    ct.add_sources(docs)
    context = ct.format_context()
    history_text = ""
    for m in (req.history or [])[-4:]:
        history_text += f"{m.get('role', 'user')}: {m.get('content', '')[:200]} " + chr(10)
    prompt = "You are a legal expert assistant. Answer based on the provided text.\n\nReference text:\n" + context + "\n\nMemory context:\n" + mem_ctx + "\n\nConversation history:\n" + history_text + "\n\nQuestion: " + query + "\n\nRequirements: Cite relevant chunks using [N] notation. If the text doesn't contain the answer, state that clearly."
    token_usage = 0
    try:
        resp = requests.post(
            f"{cfg.LLM_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {cfg.LLM_API_KEY}", "Content-Type": "application/json"},
            json={"model": cfg.LLM_MODEL, "messages": [{"role": "user", "content": prompt}], "temperature": 0.1, "max_tokens": 1024},
            timeout=60, verify=False
        )
        if resp.status_code != 200:
            return {"answer": f"API错误: {resp.status_code}", "citations": [], "token_usage": 0}
        data = resp.json()
        answer = data["choices"][0]["message"]["content"]
        token_usage = data.get("usage", {}).get("total_tokens", 0)
    except Exception as e:
        return {"answer": f"LLM调用异常: {str(e)}", "citations": [], "token_usage": 0}
    sources = ct.get_sources()
    citations = []
    for s in sources:
        txt = s.page_content[:200] if hasattr(s, 'page_content') else str(s)[:200]
        src = s.source if hasattr(s, 'source') else ""
        citations.append({"source": src, "content": txt})
    if cache:
        try: cache.set(query, answer)
        except: pass
    return {"answer": answer, "citations": citations, "token_usage": token_usage}