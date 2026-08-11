import os, sys, json, requests, time

# 将项目根目录添加到系统路径中，以便能够正确导入项目内的其他模块
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
import app.core.config as cfg  # 从.evn中加载配置，便于后期维护
from app.api.auth import get_user_from_token, require_user
import httpx
import asyncio
import threading
from typing import Dict, Any, AsyncGenerator
from types import SimpleNamespace
from fastapi import Request
from app.core.limiter import limiter
from app.tasks.task_store import get_active_task_for_tenant, has_failed_task_for_tenant

# 初始化结构化日志记录器，标识为 "chat" 模块
_log = StructuredLogger("chat")

def _validate_config():
    """
    验证必要的配置项是否存在。
    
    该函数会检查全局配置对象 cfg 中是否包含运行系统所必需的关键配置项（如大模型URL、密钥等）。
    如果发现缺失项，会记录错误日志并抛出 ValueError 异常。
    
    Raises:
        ValueError: 当缺少必要的配置项时抛出，错误信息中包含所有缺失的配置项名称及描述。
    """
    # 定义必需的配置项字典：键为配置属性名，值为该配置的中文描述
    required_configs = {
        'LLM_BASE_URL': '大语言模型API基础URL',
        'LLM_API_KEY': '大语言模型API密钥',
        'LLM_MODEL': '大语言模型名称',
        'CHROMA_PERSIST_DIR': '向量数据库持久化目录'
    }
    
    missing_configs = []
    # 遍历检查每个必需配置是否存在于 cfg 对象中且不为空
    for config_key, config_desc in required_configs.items():
        if not getattr(cfg, config_key, None):
            missing_configs.append(f"{config_key}({config_desc})")
    
    # 如果存在缺失配置，则抛出异常
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

# 创建一个API路由器，用于处理与聊天相关的API请求，统一添加 /api/chat 前缀
router = APIRouter(prefix="/api/chat", tags=["chat"]) 


class ChatRequest(BaseModel):
    """
    聊天请求的数据模型。
    
    用于验证和解析前端发送过来的聊天请求数据。
    
    Attributes:
        message (str): 用户当前输入的提问消息。
        history (Optional[List[dict]]): 历史对话记录列表，默认为空列表。
        stream (Optional[bool]): 是否开启 SSE (Server-Sent Events) 流式输出，默认为 True。
    """
    message: str
    history: Optional[List[dict]] = []
    stream: Optional[bool] = True  


# 内存系统缓存字典，按租户ID缓存 MemorySystem 实例，避免重复初始化
_memory_cache = {}
# 创建一个线程锁对象，用于在多线程环境下保护 _memory_cache 的并发读写
_cache_lock = threading.Lock() 


async def call_llm(prompt: str) -> str:
    """
    异步调用大语言模型 API。
    
    向配置好的大模型服务发送单次提示词，并返回生成的文本结果。该函数主要用于后台任务（如记忆总结）的非流式调用。
    
    Args:
        prompt (str): 发送给大模型的提示词。
        
    Returns:
        str: 大模型生成的文本响应；如果调用失败（网络错误、API鉴权失败等），则返回空字符串 ""。
    """
    try:
        # 创建异步 HTTP 客户端，设置超时时间为 30 秒，并开启 SSL 证书验证
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
                    "temperature": 0.1, # 设置较低的温度以获得更确定性的输出
                    "max_tokens": 512
                }
            )
            r.raise_for_status() # 检查HTTP状态码，如果请求失败（非2xx），将抛出 HTTPStatusError 异常
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


def _get_memory(tenant_id, embedder):
    """
    获取或创建指定租户的内存系统实例。
    
    使用缓存机制，如果该租户的 MemorySystem 已初始化则直接从内存中返回，
    否则创建新的实例并存入缓存。使用线程锁保证多线程下的安全创建。
    
    Args:
        tenant_id (str): 租户唯一标识符。
        embedder: 嵌入模型实例，用于记忆系统的向量化处理。
        
    Returns:
        MemorySystem: 该租户对应的记忆系统实例。
    """
    global _memory_cache
    # 尝试从缓存中获取
    memory_system = _memory_cache.get(tenant_id)
    if memory_system is None:
        # 定义该租户记忆数据的持久化存储路径
        pd = os.path.join("memory_db", tenant_id)
        # 初始化记忆系统
        memory_system = MemorySystem(
            embedding_model=embedder,
            persist_dir=pd,
            tenant_id=tenant_id
        )
        # 写入缓存
        _memory_cache[tenant_id] = memory_system
    return memory_system


# 可以在应用启动时添加一个定时任务
async def cleanup_cache():
    """
    定期清理内存缓存的后台任务。
    
    该协程函数会无限循环运行，每隔 2 小时触发一次清理操作，
    用于释放长时间未被使用或过期的内存资源。
    """
    while True:
        await asyncio.sleep(7200)  # 每2小时清理一次
        # 检查缓存对象是否具备 cleanup 方法，如果有则执行
        if hasattr(_memory_cache, "cleanup"):
            _memory_cache.cleanup()


# 全局重排序器实例
_reranker = None
# 创建一个锁对象，用于保护 _reranker 的单例实例化过程
_reranker_lock = threading.Lock() 

def _get_reranker():
    """
    获取重排序器单例实例。
    
    使用双重检查锁机制确保在多线程环境下只创建一次 Reranker 实例。
    
    Returns:
        Reranker: 重排序器实例。
    """
    global _reranker
    with _reranker_lock:
        if _reranker is None:
            _reranker = Reranker()
        return _reranker

def _build_pipeline(tenant_id: str):
    """
    构建当前请求的 RAG (检索增强生成) 处理管道。
    
    根据租户ID初始化并组装所需的各个组件：嵌入器、向量库、查询重写器、缓存、引用追踪器和记忆系统。
    
    Args:
        tenant_id (str): 租户唯一标识符，用于隔离不同租户的数据。
        
    Returns:
        SimpleNamespace: 包含所有管道组件对象的命名空间；如果构建过程中发生异常或向量库目录不存在，则返回 None。
    """
    try:
        # 1. 创建文本嵌入器
        embedder = create_embedder()
        # 2. 获取或创建记忆系统
        mem = _get_memory(tenant_id, embedder) if embedder else None
        # 3. 构建租户专属的向量库持久化路径
        persist_dir = os.path.join(cfg.CHROMA_PERSIST_DIR, tenant_id)
        if not os.path.exists(persist_dir):
            return None
        
        # 4. 初始化各个管道组件
        vector_store = Chroma(embedding_function=embedder, persist_directory=persist_dir)
        query_rewriter = QueryRewriter(api_key=cfg.LLM_API_KEY, base_url=cfg.LLM_BASE_URL)
        cache = QueryCache(cache_dir=os.path.join("cache", tenant_id))
        citation_tracker = CitationTracker()
        
        # 5. 将组件打包为 SimpleNamespace 返回，方便通过属性访问
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
    """
    处理聊天请求的入口 API 端点 (POST: /api/chat)。
    
    执行完整的 RAG 流程：验证向量库 -> 查询重写 -> 缓存检查 -> 检索上下文 -> 调用大模型生成回答。
    支持流式和非流式两种响应模式。带有速率限制（100次/分钟）。
    
    Args:
        request (Request): FastAPI 原生 Request 对象，用于速率限制。
        req (ChatRequest): 包含用户消息和历史记录的请求体。
        user (dict): 依赖注入获取的当前用户信息字典，包含 tenant_id 等。
        
    Returns:
        StreamingResponse | JSONResponse: 流式响应对象或包含完整答案的 JSON 响应。
    """
    # 初始化管道和链路追踪
    pipeline = _build_pipeline(user["tenant_id"])
    trace = TraceContext()
    trace.begin_span("total")
    trace.set_input(req.message)

    # 检查向量库是否可用
    if not pipeline or not pipeline.vector_store:
        return _handle_vector_store_error(user["tenant_id"])

    # 向量库存在但为空（已上传但未完成索引或数据损坏）
    try:
        docs_count = len(_get_all_texts(pipeline.vector_store))
    except Exception:
        docs_count = 0
    if docs_count == 0:
        return _handle_vector_store_error(user["tenant_id"])

    # 处理查询重写
    query = _process_query(req.message, pipeline.qr)
    
    # 检查缓存中是否已有结果
    cached_result = _check_cache(query, pipeline.cache, req.stream)
    if cached_result:
        return cached_result

    # 获取 RAG 上下文（检索 + 重排 + 构建Prompt）
    context = _get_context(query, pipeline, req.message, req.history, user["tenant_id"])
    
    # 根据前端请求选择流式或非流式响应处理
    if req.stream:
        return await _handle_streaming_response(context, req, pipeline, trace)
    else:
        return await _handle_non_streaming_response(context, req, pipeline, trace)


@router.post("/stream")
@limiter.limit("100/minute")
async def chat_stream(request: Request, req: ChatRequest, user: dict = Depends(require_user)):
    """
    流式聊天接口（兼容前端 /api/chat/stream）。
    
    本质上是强制开启流式模式，然后调用核心的 chat 方法进行处理。
    
    Args:
        request (Request): FastAPI 原生 Request 对象。
        req (ChatRequest): 包含用户消息和历史记录的请求体。
        user (dict): 依赖注入获取的当前用户信息字典。
        
    Returns:
        StreamingResponse: 流式响应对象。
    """
    req.stream = True
    return await chat(request, req, user)


def _handle_vector_store_error(tenant_id: str):
    """
    处理向量库不可用的情况，根据系统当前状态返回不同的提示信息。
    
    依次检查：是否有正在进行的后台索引任务 -> 是否有最近失败的任务 -> 是否有上传但未索引的文件 -> 确实没有上传文件。
    
    Args:
        tenant_id (str): 租户唯一标识符。
        
    Returns:
        JSONResponse: 包含针对性提示信息的 JSON 响应。
    """
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
    """
    处理查询重写逻辑。
    
    使用查询重写器将用户的原始提问转换为更适合检索的表达方式。如果重写器不可用，则使用原始消息。
    
    Args:
        message (str): 用户原始输入的消息。
        qr (QueryRewriter): 查询重写器实例。
        
    Returns:
        str: 重写后的查询语句；如果重写失败或无结果，则返回原始消息。
    """
    queries = qr.rewrite(message, num_variants=1) if qr else [message]
    return queries[0] if queries else message

def _check_cache(query, cache, is_stream):
    """
    检查缓存中是否已存在当前查询的结果。
    
    如果命中缓存，根据请求是否需要流式输出，返回对应格式的响应。
    
    Args:
        query (str): 重写后的查询语句。
        cache (QueryCache): 缓存实例。
        is_stream (bool): 是否为流式请求。
        
    Returns:
        StreamingResponse | JSONResponse | None: 如果命中缓存则返回响应对象，否则返回 None。
    """
    if not cache:
        return None
        
    cached = cache.get(query)
    if not cached:
        return None
        
    # 兼容缓存中存储的不同数据格式
    content = cached if isinstance(cached, str) else cached.get("answer", str(cached))
    if is_stream:
        return _create_streaming_response(content)
    return JSONResponse(content={"answer": content, "citations": [], "token_usage": 0})

def _create_streaming_response(content):
    """
    将已有的完整文本内容包装为 SSE 流式响应格式。
    
    主要用于缓存命中时，将非流式的缓存数据转换为前端期望的流式事件格式。
    
    Args:
        content (str): 需要发送的完整文本内容。
        
    Returns:
        StreamingResponse: 模拟的流式响应对象。
    """
    async def stream_generator():
        # 先发送内容 token 事件
        yield f"data: {json.dumps({'type': 'token', 'content': content})}\n\n"
        # 发送结束 done 事件
        yield f"data: {json.dumps({'type': 'done', 'citations': [], 'token_usage': 0})}\n\n"
    return StreamingResponse(stream_generator(), media_type="text/event-stream")

def _get_context(query, pipeline, message, history, tenant_id=None):
    """
    获取 RAG 检索上下文和记忆上下文，并构建最终的提示词。
    
    流程：获取记忆上下文 -> 混合检索 (稠密+稀疏) -> 重排序 -> 格式化引用 -> 构建 Prompt。
    
    Args:
        query (str): 重写后的查询语句。
        pipeline (SimpleNamespace): 当前请求的处理管道组件集合。
        message (str): 用户原始输入消息（用于记忆系统）。
        history (list): 对话历史。
        tenant_id (str, optional): 租户ID，用于加载稀疏向量库。
        
    Returns:
        str: 构建好的包含上下文、记忆、历史和问题的完整提示词。
    """
    # 获取记忆上下文
    mem_ctx = pipeline.mem.get_context(query) if pipeline.mem else ""
    
    # RAG 检索：获取向量库中的所有文本，用于 BM25 等稀疏检索
    all_texts = _get_all_texts(pipeline.vector_store)
    
    # 加载 BGE-M3 稀疏向量库（按租户），检索时与 BM25 + 稠密做 RRF 融合
    sparse_store = None
    if tenant_id:
        try:
            from app.retrieval.sparse_store import load_sparse_lookup
            sparse_store = load_sparse_lookup(tenant_id)
        except Exception:  # noqa: BLE001
            sparse_store = None
            
    # 初始化混合检索器并执行检索
    retriever = HybridRetriever(
        pipeline.vector_store, all_texts, k=10, sparse_store=sparse_store
    )
    docs = retriever.retrieve(query)
    
    # 对检索结果进行重排序，取 top 5
    docs = _get_reranker().rerank(query, docs, top_k=5)
    
    # 格式化上下文，将检索到的文档添加到引用追踪器中
    pipeline.ct.add_sources(docs)
    context = pipeline.ct.format_context()
    
    # 构建提示模板并返回
    return _build_prompt(context, mem_ctx, history, query)

def _get_all_texts(vector_store):
    """
    从 Chroma 向量数据库中提取所有的原始文本内容。
    
    主要用于为稀疏检索（如 BM25）提供语料库。
    
    Args:
        vector_store (Chroma): Chroma 向量库实例。
        
    Returns:
        list: 包含所有文档文本的列表；如果发生异常则返回空列表。
    """
    try:
        # 直接访问 Chroma 底层的 collection 获取所有数据
        all_data = vector_store._collection.get()
        return all_data.get("documents", []) or []
    except Exception:
        return []

def _build_prompt(context, mem_ctx, history, query):
    """
    构建发送给大语言模型的提示词模板。
    
    将检索到的参考文本、记忆上下文、对话历史和当前问题组合成结构化的 Prompt。
    
    Args:
        context (str): RAG 检索并格式化后的参考文本。
        mem_ctx (str): 长期记忆提取的上下文。
        history (list): 对话历史列表。
        query (str): 当前用户提问。
        
    Returns:
        str: 填充完毕的完整提示词字符串。
    """
    # 截取最近 4 轮对话历史，并限制单条内容长度以防止 Token 溢出
    history_text = ""
    for m in (history or [])[-4:]:
        history_text += f"{m.get('role', 'user')}: {m.get('content', '')[:200]} " + chr(10)
    
    # 定义法律专家助手的系统提示模板
    PROMPT_TEMPLATE = """你是一个法律专家助手。回答基于提供的文本。

    参考文本:
    {context}

    记忆上下文:
    {memory}

    对话历史:
    {history}

    问题: {question}

    要求: 使用 [N] 引用相关文本片段。如果文本不包含答案，请明确说明。"""
    
    # 填充模板并返回
    return PROMPT_TEMPLATE.format(
        context=context,
        memory=mem_ctx,
        history=history_text,
        question=query
    )

async def _handle_streaming_response(context, req, pipeline, trace):
    """
    处理流式响应逻辑。
    
    向大模型发起流式请求，并将返回的 SSE 数据流实时转发给前端。
    包含错误处理、心跳保活、以及响应结束后的缓存和记忆更新逻辑。
    
    Args:
        context (str): 构建好的提示词。
        req (ChatRequest): 原始请求对象。
        pipeline (SimpleNamespace): 管道组件集合。
        trace (TraceContext): 链路追踪上下文。
        
    Returns:
        StreamingResponse: SSE 流式响应对象。
    """
    async def generate():
        full_answer = ""
        start_time = time.time()
        last_yield_time = time.time()
        
        try:
            # 建立异步流式连接
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
                        # 根据不同的错误状态码返回友好的提示
                        if resp.status_code in (401, 403):
                            hint = "LLM API Key 无效或已过期，请更新 .env 中的 LLM_API_KEY 后重启服务。"
                        elif resp.status_code == 429:
                            hint = "LLM 服务限流或额度不足，请稍后重试或检查账户余额。"
                        elif not cfg.LLM_API_KEY:
                            hint = "未配置 LLM_API_KEY，请在 .env 中填写后重启服务。"
                        else:
                            hint = f"LLM 服务返回错误（HTTP {resp.status_code}）：{raw[:200]}"
                        # 发送错误事件给前端
                        yield f"data: {json.dumps({'type': 'token', 'content': '[系统] ' + hint})}\n\n"
                        yield f"data: {json.dumps({'type': 'error', 'content': hint})}\n\n"
                        return

                    # 逐行读取 SSE 响应流
                    async for line in resp.aiter_lines():
                        if line and line.startswith("data: "):
                            data_str = line[6:]
                            if data_str == "[DONE]": break
                            
                            try:
                                chunk = json.loads(data_str)
                                # 提取增量 token
                                token = chunk["choices"][0].get("delta", {}).get("content", "")
                                if token:
                                    full_answer += token
                                    # 将 token 实时推送到前端
                                    yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"
                                    last_yield_time = time.time()
                            except json.JSONDecodeError:
                                continue
                            
                            # 心跳检测：如果超过 30 秒没有新内容产生，发送空心跳保持连接
                            if time.time() - last_yield_time > 30:
                                yield f"data: {json.dumps({'type': 'token', 'content': ''})}\n\n"
                                last_yield_time = time.time()
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"
            return
        
        # 流结束后的后处理：更新缓存和记忆系统
        await _handle_post_processing(req.message, full_answer, pipeline)
        
        # 获取引用列表并发送结束信号
        citations = _get_citations(pipeline.ct)
        yield f"data: {json.dumps({'type': 'done', 'citations': citations, 'token_usage': 0})}\n\n"
        
        # 记录监控指标
        record_query(
            duration_ms=(time.time() - start_time) * 1000,
            token_usage=0,
            success=True,
            source="api_stream"
        )
    
    return StreamingResponse(generate(), media_type="text/event-stream")

async def _handle_non_streaming_response(context, req, pipeline, trace):
    """
    处理非流式响应逻辑。
    
    向大模型发起普通请求，等待完整结果返回后，一次性以 JSON 格式返回给前端。
    
    Args:
        context (str): 构建好的提示词。
        req (ChatRequest): 原始请求对象。
        pipeline (SimpleNamespace): 管道组件集合。
        trace (TraceContext): 链路追踪上下文。
        
    Returns:
        JSONResponse: 包含完整答案、引用和 token 使用情况的 JSON 响应。
    """
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
    
    # 后处理：更新缓存和记忆
    await _handle_post_processing(req.message, answer, pipeline)
    
    # 记录追踪和日志信息
    trace.end_span()
    trace.set_output(str(answer)[:500])
    trace.set_tokens(token_usage)
    trace.print_summary()
    _log.query(req.message, len(answer), token_usage, trace.total_duration_ms(), False)
    
    # 记录监控指标
    record_query(
        duration_ms=trace.total_duration_ms(),
        token_usage=token_usage,
        success=True,
        source="api"
    )
    
    return JSONResponse(content={"answer": answer, "citations": _get_citations(pipeline.ct), "token_usage": token_usage})

async def _handle_post_processing(message, answer, pipeline):
    """
    请求结束后的统一后处理逻辑：更新缓存和记忆系统。
    
    Args:
        message (str): 用户原始提问。
        answer (str): 大模型生成的回答。
        pipeline (SimpleNamespace): 管道组件集合。
    """
    # 1. 将问答对写入缓存
    if pipeline.cache:
        try:
            pipeline.cache.set(_get_query(message), answer)
        except Exception as e:
            _log.error(f"缓存写入失败: {str(e)}")
    
    # 2. 将问答对写入记忆系统，并触发后台任务（如记忆总结）
    if pipeline.mem:
        try:
            pipeline.mem.add("user", message)
            pipeline.mem.add("assistant", answer)
            pipeline.mem.trigger_background_jobs(call_llm)
        except Exception as e:
            _log.error(f"记忆更新失败: {str(e)}")

def _get_citations(context_tracker):
    """
    从引用追踪器中提取格式化的引用列表。
    
    Args:
        context_tracker (CitationTracker): 引用追踪器实例。
        
    Returns:
        list: 格式化后的引用列表，每个元素包含 source (来源) 和 content (内容片段)。
    """
    sources = context_tracker.get_sources()
    return [{"source": s.filename or "未知来源",
             "content": (s.content[:200] if s.content else "")}
            for s in sources]
