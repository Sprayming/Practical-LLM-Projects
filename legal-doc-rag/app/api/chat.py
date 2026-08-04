import os, sys, json, requests, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from fastapi import APIRouter, HTTPException, Depends, Header
from fastapi.responses import StreamingResponse, JSONResponse 
from pydantic import BaseModel
from typing import List, Optional
from app.retrieval.embedder_factory import create_embedder
from app.retrieval.hybrid_retriever import HybridRetriever, Reranker
from app.retrieval.query_rewriter import QueryRewriter
from app.retrieval.citation import CitationTracker
from app.retrieval.cache import QueryCache
from app.memory.memory_manager import MemorySystem
from app.worker.shadow_worker import get_worker
from app.observability.tracker import TraceContext
from app.observability.structured_logger import StructuredLogger
from langchain_community.vectorstores import Chroma
import app.core.config as cfg  #从.evn中加载配置，便于后期维护
from app.api.auth import get_user_from_token
import httpx
import asyncio
import threading
from typing import Dict, Any, AsyncGenerator
from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

def _validate_config():
    """验证必要的配置项是否存在"""
    required_configs = {
        'LLM_BASE_URL': '大语言模型API基础URL',
        'LLM_API_KEY': '大语言模型API密钥',
        'LLM_MODEL': '大语言模型名称',
        'CHROMA_PERSIST_DIR': '向量数据库持久化目录'
    }
    
    missing_configs = []
    for config_key, config_desc in required_configs.items():
        if not getattr(cfg, config_key, None):
            missing_configs.append(f"{config_key}({config_desc})")
    
    if missing_configs:
        error_msg = f"缺少必要的配置项: {', '.join(missing_configs)}"
        _log.error(error_msg)
        raise ValueError(error_msg)

# 在应用启动时验证配置
try:
    _validate_config()
    _log.info("配置验证通过")
except ValueError as e:
    _log.error(f"配置验证失败: {str(e)}")
    # 可以选择在这里退出程序，或者设置默认值
    # sys.exit(1)


router = APIRouter(prefix="/api/chat", tags=["chat"]) # 创建一个API路由器，用于处理与聊天相关的API请求
_log = StructuredLogger("chat")


class ChatRequest(BaseModel):
    message: str
    history: Optional[List[dict]] = []
    stream: Optional[bool] = True # TODO: implement streaming



def _require_user(authorization: str = Header(...)) -> dict:
    token = authorization.replace("Bearer ", "").strip()
    if not token:
        raise HTTPException(401, "Missing token")
    return get_user_from_token(token)


_memory_cache = {}
_cache_lock = threading.Lock() # 创建一个锁对象，用于保护缓存

# def _make_llm_func():
#     def f(prompt):
#         import requests
#         try:
#             r = requests.post(f"{cfg.LLM_BASE_URL}/chat/completions",
#                 headers={"Authorization": f"Bearer {cfg.LLM_API_KEY}", "Content-Type": "application/json"},
#                 json={"model": cfg.LLM_MODEL, "messages": [{"role": "user", "content": prompt}], "temperature": 0.1, "max_tokens": 512},
#                 timeout=30, verify=False)
#             return r.json()["choices"][0]["message"]["content"]
#         except:
#             return ""
#     return f

async def call_llm(prompt: str) -> str:
    """
    异步调用大语言模型 API。

    Args:
        prompt (str): 发送给大模型的提示词。
c
    Returns:
        str: 大模型生成的文本响应，如果调用失败则返回空字符串。
    """
    try:
        async with httpx.AsyncClient(timeout=30, verify=False) as client:
            r = await client.post(
                f"{cfg.LLM_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {cfg.LLM_API_KEY}", 
                    "Content-Type": "application/json"
                },
                json={
                    "model": cfg.LLM_MODEL, 
                    "messages": [{"role": "user", "content": prompt}], 
                    "temperature": 0.1, 
                    "max_tokens": 512
                }
            )
            r.raise_for_status() # 如果请求失败，将抛出异常 检查HTTP状态码
            return r.json()["choices"][0]["message"]["content"]
    except httpx.HTTPStatusError as e:
        _log.error(f"LLM API 返回错误状态码: {e.response.status_code}")
        return ""
    except httpx.RequestError as e:
        _log.error(f"LLM API 请求失败: {str(e)}")
        return ""
    except Exception as e:
        _log.error(f"LLM 调用未知错误: {str(e)}")
        return ""


    

# def _get_memory(tenant_id, embedder):
#     global _memory_cache
#     with _cache_lock:
#         if tenant_id not in _memory_cache:
#             pd = os.path.join("memory_db", tenant_id)
#             _memory_cache[tenant_id] = MemorySystem(embedding_model=embedder, persist_dir=pd, tenant_id=tenant_id)
#         return _memory_cache[tenant_id]


def _get_memory(tenant_id, embedder):
    global _memory_cache
    memory_system = _memory_cache.get(tenant_id)
    if memory_system is None:
        pd = os.path.join("memory_db", tenant_id)
        memory_system = MemorySystem(
            embedding_model=embedder,
            persist_dir=pd,
            tenant_id=tenant_id
        )
        _memory_cache.put(tenant_id, memory_system)
    return memory_system

# 可以在应用启动时添加一个定时任务
async def cleanup_cache():
    while True:
        await asyncio.sleep(7200)  # 每2小时清理一次
        _memory_cache.cleanup()


_reranker = None
_reranker_lock = threading.Lock() # 创建一个锁对象，用于保护 _reranker
def _get_reranker():
    global _reranker
    with _reranker_lock:
        if _reranker is None:
            _reranker = Reranker()
        return _reranker

def _build_pipeline(tenant_id: str):
    try:
        embedder = create_embedder()
        persist_dir = os.path.join(cfg.CHROMA_PERSIST_DIR, tenant_id)
        if not os.path.exists(persist_dir):
            return None, None, None, None, None
        vector_store = Chroma(embedding_function=embedder, persist_directory=persist_dir)
        query_rewriter = QueryRewriter(api_key=cfg.LLM_API_KEY, base_url=cfg.LLM_BASE_URL)
        cache = QueryCache(cache_dir=os.path.join("cache", tenant_id))
        citation_tracker = CitationTracker()
        return embedder, vector_store, query_rewriter, cache, citation_tracker
    except Exception as e:
        _log.error(f"管道构建失败: {str(e)}")
        return None, None, None, None, None

limiter = Limiter(key_func=get_remote_address)

@router.post("")
@limiter.limit("100/minute")
async def chat(req: ChatRequest,user: dict = Depends(_require_user)):
    embedder, vector_store, qr, cache, ct = _build_pipeline(user["tenant_id"])
    mem = _get_memory(user["tenant_id"], embedder) if embedder else None
    trace = TraceContext()
    trace.begin_span("total")
async def chat(req: ChatRequest, user: dict = Depends(_require_user)):
    embedder, vector_store, qr, cache, ct = _build_pipeline(user["tenant_id"])
    mem = _get_memory(user["tenant_id"], embedder) if embedder else None
    trace = TraceContext()
    trace.begin_span("total")
    trace.set_input(req.message)

    #1.检查向量库
    if vector_store is None:
        err_msg = {"answer": "请先上传文档", "citations": [], "token_usage": 0}
        #无论是流式还是非流式，错误时都返回JSON格式
        return JSONResponse(content=err_msg)

    #2.检查query查询重写
    queries = qr.rewrite(req.message, num_variants=1) if qr else [req.message]
    query = queries[0] if queries else req.message

    #3.获取记忆以及上下文
    mem_ctx = mem.get_context(query) if mem else ""
    cached = cache.get(query) if cache else None

    #4.命中缓存的处理：流式还是非流式返回
    if cached:
        content = cached if isinstance(cached, str) else cached.get("answer", str(cached))
        if req.stream:
            #流式缓存：逐字返回类似于打字机
            async def _cached_stream(): 
                yield f"data: {json.dumps({'type': 'token', 'content': content})}\n\n"
                yield f"data: {json.dumps({'type': 'done', 'citations': [], 'token_usage': 0})}\n\n"
            return StreamingResponse(_cached_stream(), media_type="text/event-stream")
        else:
            #非流式缓存：直接返回
            return JSONResponse(content={"answer": content, "citations": [], "token_usage": 0})

    #5.RAG检索
    all_texts = []
    try:
        all_data = vector_store._collection.get()
        all_texts = all_data.get("documents", []) or []
    except Exception:
        pass

    retriever = HybridRetriever(vector_store, all_texts, k=10)
    docs = retriever.retrieve(query)
    docs = _get_reranker().rerank(query, docs, top_k=5)
    ct.add_sources(docs)
    context = ct.format_context()

    #6.LLM生成,拼接Prompt
    history_text = ""
    for m in (req.history or [])[-4:]:
        history_text += f"{m.get('role', 'user')}: {m.get('content', '')[:200]} " + chr(10)
    PROMPT_TEMPLATE = """你是一个法律专家助手。回答基于提供的文本。

    参考文本:
    {context}

    记忆上下文:
    {memory}

    对话历史:
    {history}

    问题: {question}

    要求: 使用 [N] 引用相关文本片段。如果文本不包含答案，请明确说明。"""

    prompt = PROMPT_TEMPLATE.format(
        context=context,
        memory=mem_ctx,
        history=history_text,
        question=query
    )


    # ==========================================
    # 7. 核心分流：根据 req.stream 走不同的大模型调用逻辑
    # ==========================================
    
    if req.stream:
        # 【流式响应分支】
        async def generate() -> AsyncGenerator[str, None]:
            full_answer = ""
            last_yield_time = time.time() # 记录最后一次 yield 的时间
            try:
                # 👉 使用 httpx 异步流式请求
                async with httpx.AsyncClient(timeout=60, verify=False) as client:
                    async with client.stream("POST",
                        f"{cfg.LLM_BASE_URL}/chat/completions",
                        headers={"Authorization": f"Bearer {cfg.LLM_API_KEY}", "Content-Type": "application/json"},
                        json={"model": cfg.LLM_MODEL, "messages": [{"role": "user", "content": prompt}], "stream": True, "temperature": 0.1, "max_tokens": 1024}
                    ) as resp:
                        async for line in resp.aiter_lines():
                            if line and line.startswith("data: "):
                                data_str = line[6:]
                                if data_str == "[DONE]":break
                                try:
                                    chunk = json.loads(data_str)
                                    token = chunk["choices"][0].get("delta", {}).get("content", "")
                                    if token:
                                        full_answer += token
                                        yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"
                                        last_yield_time = time.time() # 更新最后一次 yield 的时间
                                except json.JSONDecodeError:
                                    continue

                                #检查是否需要发送心跳检测，防止连接超时断连
                                current_time = time.time()
                                if current_time - last_yield_time > 30:
                                    yield f"data: {json.dumps({'type': 'token', 'content': ''})}\n\n"
                                    last_yield_time = time.time() # 更新最后一次 yield 的时间
                           
            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"
                return
                
            # 流式结束后，处理引用、缓存和记忆
            sources = ct.get_sources()
            citations = [{"source": s.source if hasattr(s, 'source') else "", "content": s.page_content[:200] if hasattr(s, 'page_content') else str(s)[:200]} for s in sources]
            
            # if cache:
            #     try: cache.set(query, full_answer)
            #     except Exception as e:
            #         _log.error(f"内存更新失败: {str(e)}") # 👉 记录异常日志以及具体的错误
            # if mem:
            #     try:
            #         mem.add("user", req.message)
            #         mem.add("assistant", full_answer)
            #         mem.trigger_background_jobs(call_llm)  # 👉 传入异步函数引用
            #     except Exception as e:
            #          _log.error(f"内存更新失败: {str(e)}") # 👉 记录异常日志以及具体的错误

         
            # 1. 处理缓存
            if cache:
                try:
                    cache.set(query, full_answer)
                except IOError as e:
                    # 磁盘IO错误（如磁盘满、权限问题）
                    _log.error(f"缓存写入IO错误: {str(e)}")
                    # 可以考虑发送告警通知运维
                except MemoryError as e:
                    # 内存不足错误
                    _log.error(f"缓存内存不足: {str(e)}")
                    # 可以考虑清理其他缓存或降级处理
                except Exception as e:
                    # 其他未知错误
                    _log.error(f"缓存写入失败: {str(e)}")
                    # 记录完整的错误堆栈
                    _log.exception("缓存写入详细错误")

            # 2. 处理记忆系统
            if mem:
                try:
                    # 先保存用户输入
                    mem.add("user", req.message)
                    # 再保存助手回答
                    mem.add("assistant", full_answer)
                    # 触发后台任务（如记忆摘要、向量化等）
                    mem.trigger_background_jobs(call_llm)
                except MemoryError as e:
                    # 内存系统错误（如数据库连接失败）
                    _log.error(f"记忆系统错误: {str(e)}")
                    # 可以考虑降级处理，比如暂时禁用记忆功能
                except Exception as e:
                    # 其他未知错误
                    _log.error(f"记忆系统更新失败: {str(e)}")
                    # 记录完整的错误堆栈
                    _log.exception("记忆系统详细错误")

                
            yield f"data: {json.dumps({'type': 'done', 'citations': citations, 'token_usage': 0})}\n\n"
            
        return StreamingResponse(generate(), media_type="text/event-stream")
        
    else:
        # 【非流式响应分支】
        trace.begin_span("llm")
        token_usage = 0
        try:
            # 👉 使用 httpx 异步非流式请求
            async with httpx.AsyncClient(timeout=60, verify=False) as client:
                r = await client.post(
                    f"{cfg.LLM_BASE_URL}/chat/completions",
                    headers={"Authorization": f"Bearer {cfg.LLM_API_KEY}", "Content-Type": "application/json"},
                    json={"model": cfg.LLM_MODEL, "messages": [{"role": "user", "content": prompt}], "temperature": 0.1, "max_tokens": 1024}
                )
                r.raise_for_status()
                data = r.json()
                answer = data["choices"][0]["message"]["content"]
                token_usage = data.get("usage", {}).get("total_tokens", 0)
        except Exception as e:
            return JSONResponse(content={"answer": f"LLM调用异常: {str(e)}", "citations": [], "token_usage": 0})
            
        # 非流式结束后，处理引用、缓存和记忆
        sources = ct.get_sources()
        citations = [{"source": s.source if hasattr(s, 'source') else "", "content": s.page_content[:200] if hasattr(s, 'page_content') else str(s)[:200]} for s in sources]
        
        # if cache:
        #     try: cache.set(query, answer)
        #     except Exception as e:
        #         _log.error(f"内存更新失败: {str(e)}") # 👉 记录异常日志以及具体的错误
        if cache:
            try:
                cache.set(query, answer)
            except IOError as e:
                _log.error(f"缓存IO错误: {str(e)}")
            except Exception as e:
                _log.error(f"缓存写入失败: {str(e)}")

        if mem:
            try:
                mem.add("user", req.message)
                mem.add("assistant", answer)
                mem.trigger_background_jobs(call_llm)
            except MemoryError as e:
                _log.error(f"内存错误: {str(e)}")
            except Exception as e:
                _log.error(f"内存更新失败: {str(e)}")

        trace.end_span()
        trace.set_output(str(answer)[:500])
        trace.set_tokens(token_usage)
        trace.print_summary()
        _log.query(req.message, len(answer), token_usage, trace.total_duration_ms(), False)
        
        # 👉 必须使用 JSONResponse 返回，保证与流式分支的返回类型兼容
        return JSONResponse(content={"answer": answer, "citations": citations, "token_usage": token_usage})