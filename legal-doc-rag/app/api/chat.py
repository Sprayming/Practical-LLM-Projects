import os, sys, json, requests, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from fastapi import APIRouter, HTTPException, Depends
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
from app.observability.monitoring import record_query
from langchain_community.vectorstores import Chroma
import app.core.config as cfg  #从.evn中加载配置，便于后期维护
from app.api.auth import get_user_from_token, require_user
import httpx
import asyncio
import threading
from typing import Dict, Any, AsyncGenerator
from types import SimpleNamespace
from fastapi import Request
from app.core.limiter import limiter
from app.tasks.task_store import get_active_task_for_tenant, has_failed_task_for_tenant

_log = StructuredLogger("chat")

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


class ChatRequest(BaseModel):
    """定义聊天请求的模型"""
    message: str
    history: Optional[List[dict]] = []
    stream: Optional[bool] = True  # SSE 流式输出（默认开启，见 chat 端点的流式分支）




_memory_cache = {}
_cache_lock = threading.Lock() # 创建一个锁对象，用于保护缓存

# def _make_llm_func():
#     def f(prompt):
#         import requests
#         try:
#             r = requests.post(f"{cfg.LLM_BASE_URL}/chat/completions",
#                 headers={"Authorization": f"Bearer {cfg.LLM_API_KEY}", "Content-Type": "application/json"},
#                 json={"model": cfg.LLM_MODEL, "messages": [{"role": "user", "content": prompt}], "temperature": 0.1, "max_tokens": 512},
#                 timeout=30, verify=True)
#             return r.json()["choices"][0]["message"]["content"]
#         except:
#             return ""
#     return f

async def call_llm(prompt: str) -> str:
    """
    异步调用大语言模型 API。

    Args:
        prompt (str): 发送给大模型的提示词。
    Returns:
        str: 大模型生成的文本响应，如果调用失败则返回空字符串。
    """
    try:
        async with httpx.AsyncClient(timeout=30, verify=True) as client:
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
    """获取内存系统"""
    global _memory_cache
    memory_system = _memory_cache.get(tenant_id)
    if memory_system is None:
        pd = os.path.join("memory_db", tenant_id)
        memory_system = MemorySystem(
            embedding_model=embedder,
            persist_dir=pd,
            tenant_id=tenant_id
        )
        _memory_cache[tenant_id] = memory_system
    return memory_system

# 可以在应用启动时添加一个定时任务
async def cleanup_cache():
    """定期清理内存缓存"""
    while True:
        await asyncio.sleep(7200)  # 每2小时清理一次
        if hasattr(_memory_cache, "cleanup"):
            _memory_cache.cleanup()


_reranker = None
_reranker_lock = threading.Lock() # 创建一个锁对象，用于保护 _reranker
def _get_reranker():
    """获取重排序器"""
    global _reranker
    with _reranker_lock:
        if _reranker is None:
            _reranker = Reranker()
        return _reranker

def _build_pipeline(tenant_id: str):
    """构建管道"""
    try:
        embedder = create_embedder()
        mem = _get_memory(tenant_id, embedder) if embedder else None
        persist_dir = os.path.join(cfg.CHROMA_PERSIST_DIR, tenant_id)
        if not os.path.exists(persist_dir):
            return None
        vector_store = Chroma(embedding_function=embedder, persist_directory=persist_dir)
        query_rewriter = QueryRewriter(api_key=cfg.LLM_API_KEY, base_url=cfg.LLM_BASE_URL)
        cache = QueryCache(cache_dir=os.path.join("cache", tenant_id))
        citation_tracker = CitationTracker()
        return SimpleNamespace(
            embedder=embedder,
            vector_store=vector_store,
            qr=query_rewriter,
            cache=cache,
            ct=citation_tracker,
            mem=mem,
        )
    except Exception as e:
        _log.error(f"管道构建失败: {str(e)}")
        return None

@router.post("")
@limiter.limit("100/minute")
async def chat(request: Request, req: ChatRequest, user: dict = Depends(require_user)):
    """处理聊天请求的入口函数"""
    # 初始化管道和追踪
    pipeline = _build_pipeline(user["tenant_id"])
    trace = TraceContext()
    trace.begin_span("total")
    trace.set_input(req.message)

    # 检查向量库
    if not pipeline or not pipeline.vector_store:
        return _handle_vector_store_error(user["tenant_id"])

    # 向量库存在但为空（已上传但未完成索引或数据损坏）
    try:
        docs_count = len(_get_all_texts(pipeline.vector_store))
    except Exception:
        docs_count = 0
    if docs_count == 0:
        return _handle_vector_store_error(user["tenant_id"])

    # 处理查询
    query = _process_query(req.message, pipeline.qr)
    
    # 检查缓存
    cached_result = _check_cache(query, pipeline.cache, req.stream)
    if cached_result:
        return cached_result

    # 获取上下文
    context = _get_context(query, pipeline, req.message, req.history, user["tenant_id"])
    
    # 处理响应
    if req.stream:
        return await _handle_streaming_response(context, req, pipeline, trace)
    else:
        return await _handle_non_streaming_response(context, req, pipeline, trace)


@router.post("/stream")
@limiter.limit("100/minute")
async def chat_stream(request: Request, req: ChatRequest, user: dict = Depends(require_user)):
    """流式聊天接口（兼容前端 /api/chat/stream）。"""
    req.stream = True
    return await chat(request, req, user)


def _handle_vector_store_error(tenant_id: str):
    """处理向量库不可用的情况，按状态给出不同提示。"""
    # 1. 有正在后台索引的任务
    active = get_active_task_for_tenant(tenant_id)
    if active:
        return JSONResponse(content={
            "answer": (
                f"文档「{active['filename']}」正在后台索引中"
                f"（{active['stage']}，进度 {active['progress']}%），请稍候再问。"
            ),
            "citations": [],
            "token_usage": 0,
            "task_id": active["task_id"],
        })

    # 2. 最近有索引失败的任务
    failed = has_failed_task_for_tenant(tenant_id)
    if failed:
        return JSONResponse(content={
            "answer": (
                f"文档「{failed['filename']}」索引失败（{failed.get('error', '未知错误')}），"
                "请删除后重新上传。"
            ),
            "citations": [],
            "token_usage": 0,
        })

    # 3. 已上传文件但向量库尚未建立（服务重启/索引中断）
    upload_dir = os.path.join(cfg.UPLOAD_DIR, tenant_id)
    has_uploads = os.path.exists(upload_dir) and any(
        f.lower().endswith(".pdf") for f in os.listdir(upload_dir)
    )
    if has_uploads:
        return JSONResponse(content={
            "answer": (
                "检测到您已上传文档，但向量索引尚未完成或已被中断，"
                "系统正在后台恢复索引，请稍候再试。"
            ),
            "citations": [],
            "token_usage": 0,
        })

    # 4. 确实没有上传过文档
    return JSONResponse(content={"answer": "请先上传文档", "citations": [], "token_usage": 0})

def _process_query(message, qr):
    """处理查询重写"""
    queries = qr.rewrite(message, num_variants=1) if qr else [message]
    return queries[0] if queries else message

def _check_cache(query, cache, is_stream):
    """检查缓存并返回结果"""
    if not cache:
        return None
        
    cached = cache.get(query)
    if not cached:
        return None
        
    content = cached if isinstance(cached, str) else cached.get("answer", str(cached))
    if is_stream:
        return _create_streaming_response(content)
    return JSONResponse(content={"answer": content, "citations": [], "token_usage": 0})

def _create_streaming_response(content):
    """创建流式响应"""
    async def stream_generator():
        yield f"data: {json.dumps({'type': 'token', 'content': content})}\n\n"
        yield f"data: {json.dumps({'type': 'done', 'citations': [], 'token_usage': 0})}\n\n"
    return StreamingResponse(stream_generator(), media_type="text/event-stream")

def _get_context(query, pipeline, message, history, tenant_id=None):
    """获取RAG上下文和记忆上下文"""
    # 获取记忆上下文
    mem_ctx = pipeline.mem.get_context(query) if pipeline.mem else ""
    
    # RAG检索
    all_texts = _get_all_texts(pipeline.vector_store)
    # 加载 BGE-M3 稀疏向量库（按租户），检索时与 BM25 + 稠密做 RRF 融合
    sparse_store = None
    if tenant_id:
        try:
            from app.retrieval.sparse_store import load_sparse_lookup

            sparse_store = load_sparse_lookup(tenant_id)
        except Exception:  # noqa: BLE001
            sparse_store = None
    retriever = HybridRetriever(
        pipeline.vector_store, all_texts, k=10, sparse_store=sparse_store
    )
    docs = retriever.retrieve(query)
    docs = _get_reranker().rerank(query, docs, top_k=5)
    
    # 格式化上下文
    pipeline.ct.add_sources(docs)
    context = pipeline.ct.format_context()
    
    # 构建提示模板
    return _build_prompt(context, mem_ctx, history, query)

def _get_all_texts(vector_store):
    """获取所有文本"""
    try:
        all_data = vector_store._collection.get()
        return all_data.get("documents", []) or []
    except Exception:
        return []

def _build_prompt(context, mem_ctx, history, query):
    """构建提示模板"""
    history_text = ""
    for m in (history or [])[-4:]:
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
    
    return PROMPT_TEMPLATE.format(
        context=context,
        memory=mem_ctx,
        history=history_text,
        question=query
    )

async def _handle_streaming_response(context, req, pipeline, trace):
    """处理流式响应"""
    async def generate():
        full_answer = ""
        start_time = time.time()
        last_yield_time = time.time()
        
        try:
            async with httpx.AsyncClient(timeout=60, verify=True) as client:
                async with client.stream("POST",
                    f"{cfg.LLM_BASE_URL}/chat/completions",
                    headers={"Authorization": f"Bearer {cfg.LLM_API_KEY}", "Content-Type": "application/json"},
                    json={"model": cfg.LLM_MODEL, "messages": [{"role": "user", "content": context}], "stream": True, "temperature": 0.1, "max_tokens": 1024}
                ) as resp:
                    # 必须先检查状态码：出错时响应体是普通 JSON 而非 SSE，
                    # 下面的 `data: ` 循环会一个 token 都取不到，导致前端「提问后毫无反应」
                    # 的静默失败（日志里也看不到任何报错）。
                    if resp.status_code != 200:
                        raw = (await resp.aread()).decode("utf-8", "replace")
                        _log.error(f"LLM 流式调用失败 status={resp.status_code} body={raw[:500]}")
                        if resp.status_code in (401, 403):
                            hint = "LLM API Key 无效或已过期，请更新 .env 中的 LLM_API_KEY 后重启服务。"
                        elif resp.status_code == 429:
                            hint = "LLM 服务限流或额度不足，请稍后重试或检查账户余额。"
                        elif not cfg.LLM_API_KEY:
                            hint = "未配置 LLM_API_KEY，请在 .env 中填写后重启服务。"
                        else:
                            hint = f"LLM 服务返回错误（HTTP {resp.status_code}）：{raw[:200]}"
                        yield f"data: {json.dumps({'type': 'token', 'content': '[系统] ' + hint})}\n\n"
                        yield f"data: {json.dumps({'type': 'error', 'content': hint})}\n\n"
                        return

                    async for line in resp.aiter_lines():
                        if line and line.startswith("data: "):
                            data_str = line[6:]
                            if data_str == "[DONE]": break
                            
                            try:
                                chunk = json.loads(data_str)
                                token = chunk["choices"][0].get("delta", {}).get("content", "")
                                if token:
                                    full_answer += token
                                    yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"
                                    last_yield_time = time.time()
                            except json.JSONDecodeError:
                                continue
                            
                            # 心跳检测
                            if time.time() - last_yield_time > 30:
                                yield f"data: {json.dumps({'type': 'token', 'content': ''})}\n\n"
                                last_yield_time = time.time()
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"
            return
        
        # 处理缓存和记忆
        await _handle_post_processing(req.message, full_answer, pipeline)
        
        # 处理引用和结束信号
        citations = _get_citations(pipeline.ct)
        yield f"data: {json.dumps({'type': 'done', 'citations': citations, 'token_usage': 0})}\n\n"
        
        # 记录指标
        record_query(
            duration_ms=(time.time() - start_time) * 1000,
            token_usage=0,
            success=True,
            source="api_stream"
        )
    
    return StreamingResponse(generate(), media_type="text/event-stream")

async def _handle_non_streaming_response(context, req, pipeline, trace):
    """处理非流式响应"""
    trace.begin_span("llm")
    token_usage = 0
    
    try:
        async with httpx.AsyncClient(timeout=60, verify=True) as client:
            r = await client.post(
                f"{cfg.LLM_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {cfg.LLM_API_KEY}", "Content-Type": "application/json"},
                json={"model": cfg.LLM_MODEL, "messages": [{"role": "user", "content": context}], "temperature": 0.1, "max_tokens": 1024}
            )
            r.raise_for_status()
            data = r.json()
            answer = data["choices"][0]["message"]["content"]
            token_usage = data.get("usage", {}).get("total_tokens", 0)
    except Exception as e:
        return JSONResponse(content={"answer": f"LLM调用异常: {str(e)}", "citations": [], "token_usage": 0})
    
    # 处理缓存和记忆
    await _handle_post_processing(req.message, answer, pipeline)
    
    # 处理追踪和日志
    trace.end_span()
    trace.set_output(str(answer)[:500])
    trace.set_tokens(token_usage)
    trace.print_summary()
    _log.query(req.message, len(answer), token_usage, trace.total_duration_ms(), False)
    
    # 记录指标
    record_query(
        duration_ms=trace.total_duration_ms(),
        token_usage=token_usage,
        success=True,
        source="api"
    )
    
    return JSONResponse(content={"answer": answer, "citations": _get_citations(pipeline.ct), "token_usage": token_usage})

async def _handle_post_processing(message, answer, pipeline):
    """处理缓存和记忆"""
    # 处理缓存
    if pipeline.cache:
        try:
            pipeline.cache.set(_get_query(message), answer)
        except Exception as e:
            _log.error(f"缓存写入失败: {str(e)}")
    
    # 处理记忆
    if pipeline.mem:
        try:
            pipeline.mem.add("user", message)
            pipeline.mem.add("assistant", answer)
            pipeline.mem.trigger_background_jobs(call_llm)
        except Exception as e:
            _log.error(f"记忆更新失败: {str(e)}")

def _get_citations(context_tracker):
    """获取引用列表"""
    sources = context_tracker.get_sources()
    return [{"source": s.filename or "未知来源",
             "content": (s.content[:200] if s.content else "")}
            for s in sources]



# async def chat(request: Request, req: ChatRequest, user: dict = Depends(require_user)):
#     embedder, vector_store, qr, cache, ct = _build_pipeline(user["tenant_id"])
#     mem = _get_memory(user["tenant_id"], embedder) if embedder else None
#     trace = TraceContext()
#     trace.begin_span("total")
#     trace.set_input(req.message)

#     #1.检查向量库
#     if vector_store is None:
#         err_msg = {"answer": "请先上传文档", "citations": [], "token_usage": 0}
#         #无论是流式还是非流式，错误时都返回JSON格式
#         return JSONResponse(content=err_msg)

#     #2.检查query查询重写
#     queries = qr.rewrite(req.message, num_variants=1) if qr else [req.message]
#     query = queries[0] if queries else req.message

#     #3.获取记忆以及上下文
#     mem_ctx = mem.get_context(query) if mem else ""
#     cached = cache.get(query) if cache else None

#     #4.命中缓存的处理：流式还是非流式返回
#     if cached:
#         content = cached if isinstance(cached, str) else cached.get("answer", str(cached))
#         if req.stream:
#             #流式缓存：逐字返回类似于打字机
#             async def _cached_stream(): 
#                 yield f"data: {json.dumps({'type': 'token', 'content': content})}\n\n"
#                 yield f"data: {json.dumps({'type': 'done', 'citations': [], 'token_usage': 0})}\n\n"
#             return StreamingResponse(_cached_stream(), media_type="text/event-stream")
#         else:
#             #非流式缓存：直接返回
#             return JSONResponse(content={"answer": content, "citations": [], "token_usage": 0})

#     #5.RAG检索
#     all_texts = []
#     try:
#         all_data = vector_store._collection.get()
#         all_texts = all_data.get("documents", []) or []
#     except Exception:
#         pass

#     retriever = HybridRetriever(vector_store, all_texts, k=10)
#     docs = retriever.retrieve(query)
#     docs = _get_reranker().rerank(query, docs, top_k=5)
#     ct.add_sources(docs)
#     context = ct.format_context()

#     #6.LLM生成,拼接Prompt
#     history_text = ""
#     for m in (req.history or [])[-4:]:
#         history_text += f"{m.get('role', 'user')}: {m.get('content', '')[:200]} " + chr(10)
#     PROMPT_TEMPLATE = """你是一个法律专家助手。回答基于提供的文本。

#     参考文本:
#     {context}

#     记忆上下文:
#     {memory}

#     对话历史:
#     {history}

#     问题: {question}

#     要求: 使用 [N] 引用相关文本片段。如果文本不包含答案，请明确说明。"""

#     prompt = PROMPT_TEMPLATE.format(
#         context=context,
#         memory=mem_ctx,
#         history=history_text,
#         question=query
#     )


#     # ==========================================
#     # 7. 核心分流：根据 req.stream 走不同的大模型调用逻辑
#     # ==========================================
    
#     if req.stream:
#         # 【流式响应分支】
#         async def generate() -> AsyncGenerator[str, None]:
#             full_answer = ""
#             start_time = time.time()  # Record start time for metrics
#             last_yield_time = time.time() # 记录最后一次 yield 的时间
#             try:
#                 # 👉 使用 httpx 异步流式请求
#                 async with httpx.AsyncClient(timeout=60, verify=True) as client:
#                     async with client.stream("POST",
#                         f"{cfg.LLM_BASE_URL}/chat/completions",
#                         headers={"Authorization": f"Bearer {cfg.LLM_API_KEY}", "Content-Type": "application/json"},
#                         json={"model": cfg.LLM_MODEL, "messages": [{"role": "user", "content": prompt}], "stream": True, "temperature": 0.1, "max_tokens": 1024}
#                     ) as resp:
#                         async for line in resp.aiter_lines():
#                             if line and line.startswith("data: "):
#                                 data_str = line[6:]
#                                 if data_str == "[DONE]":break
#                                 try:
#                                     chunk = json.loads(data_str)
#                                     token = chunk["choices"][0].get("delta", {}).get("content", "")
#                                     if token:
#                                         full_answer += token
#                                         yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"
#                                         last_yield_time = time.time() # 更新最后一次 yield 的时间
#                                 except json.JSONDecodeError:
#                                     continue

#                                 #检查是否需要发送心跳检测，防止连接超时断连
#                                 current_time = time.time()
#                                 if current_time - last_yield_time > 30:
#                                     yield f"data: {json.dumps({'type': 'token', 'content': ''})}\n\n"
#                                     last_yield_time = time.time() # 更新最后一次 yield 的时间
                           
#             except Exception as e:
#                 yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"
#                 return
                
#             # 流式结束后，处理引用、缓存和记忆
#             sources = ct.get_sources()
#             citations = [{"source": s.source if hasattr(s, 'source') else "", "content": s.page_content[:200] if hasattr(s, 'page_content') else str(s)[:200]} for s in sources]
            
#             # if cache:
#             #     try: cache.set(query, full_answer)
#             #     except Exception as e:
#             #         _log.error(f"内存更新失败: {str(e)}") # 👉 记录异常日志以及具体的错误
#             # if mem:
#             #     try:
#             #         mem.add("user", req.message)
#             #         mem.add("assistant", full_answer)
#             #         mem.trigger_background_jobs(call_llm)  # 👉 传入异步函数引用
#             #     except Exception as e:
#             #          _log.error(f"内存更新失败: {str(e)}") # 👉 记录异常日志以及具体的错误

         
#             # 1. 处理缓存
#             if cache:
#                 try:
#                     cache.set(query, full_answer)
#                 except IOError as e:
#                     # 磁盘IO错误（如磁盘满、权限问题）
#                     _log.error(f"缓存写入IO错误: {str(e)}")
#                     # 可以考虑发送告警通知运维
#                 except MemoryError as e:
#                     # 内存不足错误
#                     _log.error(f"缓存内存不足: {str(e)}")
#                     # 可以考虑清理其他缓存或降级处理
#                 except Exception as e:
#                     # 其他未知错误
#                     _log.error(f"缓存写入失败: {str(e)}")
#                     # 记录完整的错误堆栈
#                     _log.exception("缓存写入详细错误")

#             # 2. 处理记忆系统
#             if mem:
#                 try:
#                     # 先保存用户输入
#                     mem.add("user", req.message)
#                     # 再保存助手回答
#                     mem.add("assistant", full_answer)
#                     # 触发后台任务（如记忆摘要、向量化等）
#                     mem.trigger_background_jobs(call_llm)
#                 except MemoryError as e:
#                     # 内存系统错误（如数据库连接失败）
#                     _log.error(f"记忆系统错误: {str(e)}")
#                     # 可以考虑降级处理，比如暂时禁用记忆功能
#                 except Exception as e:
#                     # 其他未知错误
#                     _log.error(f"记忆系统更新失败: {str(e)}")
#                     # 记录完整的错误堆栈
#                     _log.exception("记忆系统详细错误")

#                 # Record metrics for streaming response
#                 record_query(
#                     duration_ms=(time.time() - start_time) * 1000,
#                     token_usage=0,  # Token usage not easily available in streaming
#                     success=True,
#                     source="api_stream"
#                 )

#             yield f"data: {json.dumps({'type': 'done', 'citations': citations, 'token_usage': 0})}\n\n"
            
#         return StreamingResponse(generate(), media_type="text/event-stream")
        
#     else:
#         # 【非流式响应分支】
#         trace.begin_span("llm")
#         token_usage = 0
#         try:
#             # 👉 使用 httpx 异步非流式请求
#             async with httpx.AsyncClient(timeout=60, verify=True) as client:
#                 r = await client.post(
#                     f"{cfg.LLM_BASE_URL}/chat/completions",
#                     headers={"Authorization": f"Bearer {cfg.LLM_API_KEY}", "Content-Type": "application/json"},
#                     json={"model": cfg.LLM_MODEL, "messages": [{"role": "user", "content": prompt}], "temperature": 0.1, "max_tokens": 1024}
#                 )
#                 r.raise_for_status()
#                 data = r.json()
#                 answer = data["choices"][0]["message"]["content"]
#                 token_usage = data.get("usage", {}).get("total_tokens", 0)
#         except Exception as e:
#             return JSONResponse(content={"answer": f"LLM调用异常: {str(e)}", "citations": [], "token_usage": 0})
            
#         # 非流式结束后，处理引用、缓存和记忆
#         sources = ct.get_sources()
#         citations = [{"source": s.source if hasattr(s, 'source') else "", "content": s.page_content[:200] if hasattr(s, 'page_content') else str(s)[:200]} for s in sources]
        
#         # if cache:
#         #     try: cache.set(query, answer)
#         #     except Exception as e:
#         #         _log.error(f"内存更新失败: {str(e)}") # 👉 记录异常日志以及具体的错误
#         if cache:
#             try:
#                 cache.set(query, answer)
#             except IOError as e:
#                 _log.error(f"缓存IO错误: {str(e)}")
#             except Exception as e:
#                 _log.error(f"缓存写入失败: {str(e)}")

#         if mem:
#             try:
#                 mem.add("user", req.message)
#                 mem.add("assistant", answer)
#                 mem.trigger_background_jobs(call_llm)
#             except MemoryError as e:
#                 _log.error(f"内存错误: {str(e)}")
#             except Exception as e:
#                 _log.error(f"内存更新失败: {str(e)}")

#         trace.end_span()
#         trace.set_output(str(answer)[:500])
#         trace.set_tokens(token_usage)
#         trace.print_summary()
#         _log.query(req.message, len(answer), token_usage, trace.total_duration_ms(), False)

#         # Record metrics for monitoring
#         record_query(
#             duration_ms=trace.total_duration_ms(),
#             token_usage=token_usage,
#             success=True,
#             source="api"
#         )

#         # 👉 必须使用 JSONResponse 返回，保证与流式分支的返回类型兼容
#         return JSONResponse(content={"answer": answer, "citations": citations, "token_usage": token_usage})