
from __future__ import annotations
import os, ssl, json, tiktoken
from pathlib import Path
from dotenv import load_dotenv
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.memory.memory_manager import MemorySystem

# 网络配置
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
os.environ["CURL_CA_BUNDLE"] = ""
os.environ["REQUESTS_CA_BUNDLE"] = ""
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ["HF_HUB_OFFLINE"] = "1"
ssl._create_default_https_context = ssl._create_unverified_context
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

import requests, streamlit as st
# Heavy packages loaded lazily below
from app.observability.structured_logger import StructuredLogger
from app.memory.conversation_store import ConversationStore
from app.retrieval.cache import QueryCache

# 加载环境变量
env_path = Path(__file__).resolve().parent.parent / ".env"
if env_path.exists():
    load_dotenv(str(env_path))

# 全局配置
DEEPSEEK_API_KEY = os.getenv("LLM_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1")
TOKENIZER = tiktoken.get_encoding("cl100k_base")

# 会话状态
if "messages" not in st.session_state:
    st.session_state.messages = []
if "total_tokens" not in st.session_state:
    st.session_state.total_tokens = 0
if "summary" not in st.session_state:
    st.session_state.summary = ""
if "tenant_id" not in st.session_state:
    st.session_state.tenant_id = "default"

# 页面设置
st.set_page_config(page_title="法律文档 RAG", layout="wide")

# 自定义 CSS - 专业法律文档风格
st.markdown("""
<style>
    /* 整体主题 */
    .stApp {
        background: #f8f9fa;
    }
    .main > div {
        padding: 0 2rem 2rem 2rem;
    }
    
    /* 侧边栏 */
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #1a237e 0%, #283593 100%);
        padding-top: 1rem;
    }
    section[data-testid="stSidebar"] .st-emotion-cache-1v0mbdj {
        background: transparent;
    }
    section[data-testid="stSidebar"] p {
        color: rgba(255,255,255,0.9);
    }
    section[data-testid="stSidebar"] .st-emotion-cache-16txtl3 h1,
    section[data-testid="stSidebar"] h2,
    section[data-testid="stSidebar"] h3 {
        color: #ffffff !important;
    }
    
    /* 侧边栏品牌区域 */
    .sidebar-brand {
        background: rgba(255,255,255,0.08);
        border-radius: 12px;
        padding: 1.5rem 1rem;
        margin-bottom: 1.5rem;
        text-align: center;
        backdrop-filter: blur(10px);
    }
    .sidebar-brand h1 {
        font-size: 1.3rem;
        font-weight: 700;
        color: #ffffff !important;
        margin: 0;
        letter-spacing: 0.5px;
    }
    .sidebar-brand p {
        font-size: 0.75rem;
        color: rgba(255,255,255,0.6) !important;
        margin: 4px 0 0 0;
    }
    .sidebar-brand .icon {
        font-size: 2rem;
        margin-bottom: 0.5rem;
    }
    
    /* 侧边栏分组卡片 */
    .sidebar-card {
        background: rgba(255,255,255,0.06);
        border: 1px solid rgba(255,255,255,0.1);
        border-radius: 10px;
        padding: 0.8rem 1rem;
        margin-bottom: 0.8rem;
    }
    .sidebar-card .label {
        font-size: 0.7rem;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        color: rgba(255,255,255,0.7) !important;
        margin-bottom: 4px;
    }
    .sidebar-card .value {
        font-size: 1.1rem;
        font-weight: 600;
        color: #ffffff !important;
    }
    .sidebar-card .value small {
        font-size: 0.7rem;
        font-weight: 400;
        color: rgba(255,255,255,0.7) !important;
    }
    
    /* 侧边栏分隔线 */
    section[data-testid="stSidebar"] hr {
        border-color: rgba(255,255,255,0.1);
        margin: 1rem 0;
    }
    
    /* 主区域标题 */
    .main-title {
        display: flex;
        align-items: center;
        gap: 12px;
        padding: 1.2rem 0 0.5rem 0;
        border-bottom: 2px solid #e8eaed;
        margin-bottom: 1.5rem;
    }
    .main-title h1 {
        font-size: 1.6rem;
        font-weight: 700;
        color: #1a237e;
        margin: 0;
    }
    .main-title .badge {
        background: #e8eaf6;
        color: #283593;
        font-size: 0.65rem;
        font-weight: 600;
        padding: 2px 8px;
        border-radius: 4px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    
    /* 上传区域 */
    .upload-area {
        background: rgba(255,255,255,0.05);
        border: 2px dashed rgba(255,255,255,0.2);
        border-radius: 10px;
        padding: 1.5rem 1rem;
        text-align: center;
        transition: all 0.2s;
    }
    
    /* 欢迎提示 */
    .welcome-card {
        background: white;
        border: 1px solid #e8eaed;
        border-radius: 12px;
        padding: 2.5rem 2rem;
        text-align: center;
        max-width: 500px;
        margin: 2rem auto;
        box-shadow: 0 1px 3px rgba(0,0,0,0.04);
    }
    .welcome-card .icon {
        font-size: 3rem;
        margin-bottom: 1rem;
    }
    .welcome-card h2 {
        color: #1a237e;
        font-size: 1.3rem;
        font-weight: 600;
        margin: 0 0 0.5rem 0;
    }
    .welcome-card p {
        color: #3c4043;
        font-size: 0.9rem;
        margin: 0;
        line-height: 1.5;
    }
    .welcome-card .steps {
        text-align: left;
        margin: 1.2rem 0 0 0;
        padding: 0;
        list-style: none;
    }
    .welcome-card .steps li {
        padding: 6px 0;
        color: #5f6368;
        font-size: 0.85rem;
    }
    .welcome-card .steps li:before {
        content: "\2713";
        color: #34a853;
        font-weight: 700;
        margin-right: 8px;
    }
    
    /* 消息气泡 */
    .stChatMessage {
        border-radius: 12px !important;
        border: none !important;
        box-shadow: 0 1px 3px rgba(0,0,0,0.06) !important;
        margin-bottom: 0.8rem !important;
    }
    .stChatMessage[data-testid="chatMessage"]:has([data-testid="chatAvatarIcon-user"]) {
        background: #e8f0fe !important;
    }
    .stChatMessage[data-testid="chatMessage"]:has([data-testid="chatAvatarIcon-assistant"]) {
        background: #ffffff !important;
    }
    
    /* Token 信息 */
    .token-info {
        font-size: 0.7rem;
        color: #9aa0a6 !important;
        padding: 4px 0;
    }
    
    /* 反馈按钮 */
    .feedback-buttons {
        display: flex;
        gap: 8px;
        padding: 8px 0;
    }
    .feedback-buttons button {
        background: transparent;
        border: 1px solid #dadce0;
        border-radius: 6px;
        padding: 4px 12px;
        font-size: 0.8rem;
        cursor: pointer;
        transition: all 0.15s;
    }
    .feedback-buttons button:hover {
        background: #f1f3f4;
        border-color: #9aa0a6;
    }
    
    /* 成功提示 */
    .element-container:has(.stAlert) {
        max-width: 600px;
        margin: 1rem auto;
    }
    
    /* 输入框 */
    .stChatFloatingInputContainer {
        background: transparent !important;
        padding: 0 2rem 1rem 2rem !important;
        border-top: 1px solid #e8eaed !important;
    }
    
    /* 登陆页 */
    .login-box {
        max-width: 360px;
        margin: 4rem auto;
        padding: 2rem;
        background: white;
        border-radius: 12px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.08);
        text-align: center;
    }
</style>
""", unsafe_allow_html=True)

# 生产环境认证（可选, 通过 APP_PASSWORD 环境变量开启）
APP_PASSWORD = os.getenv("APP_PASSWORD", "")
if APP_PASSWORD:
    if not st.session_state.get("authenticated"):
        st.title("法律文档 RAG")
        pw = st.text_input("请输入访问密码", type="password")
        if st.button("登录"):
            if pw == APP_PASSWORD:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("密码错误")
        st.stop()

# 初始化生产组件（结构化日志、对话持久化、查询缓存）
logger = StructuredLogger("app")
conversation_store = ConversationStore()
query_cache = QueryCache()




# 侧边栏
with st.sidebar:
    st.markdown('<div class="sidebar-brand"><div class="icon">\U0001f50d</div><h1>法律文档 RAG</h1><p>智能文档问答系统</p></div>', unsafe_allow_html=True)
    
    st.markdown('<div class="sidebar-card"><div class="label">上传文档</div></div>', unsafe_allow_html=True)
    tenant_id = st.text_input("租户 ID", value=st.session_state.tenant_id, key="tenant_input", label_visibility="collapsed", placeholder="Tenant ID")
    if tenant_id != st.session_state.tenant_id:
        st.session_state.tenant_id = tenant_id
        st.session_state.messages = []
        st.session_state.summary = ""
        st.session_state.total_tokens = 0
        st.rerun()
    uploaded_file = st.file_uploader("上传 PDF", type="pdf", label_visibility="collapsed")
    st.divider()
    
    rounds = len(st.session_state.messages) // 2
    st.markdown(f'<div class="sidebar-card"><div class="label">会话统计</div><div class="value">{st.session_state.get("last_tokens", 0)} <small>当前</small></div><div class="value">{st.session_state.total_tokens} <small>总计</small></div><div style="margin-top:6px;font-size:0.8rem;color:rgba(255,255,255,0.6)">{rounds} 轮次</div></div>', unsafe_allow_html=True)
    
    if st.button("\U0001f5d1 清除历史", use_container_width=True):
        st.session_state.messages = []
        st.session_state.summary = ""
        st.session_state.total_tokens = 0
        st.rerun()
    
    st.markdown('<div style="position:fixed;bottom:1rem;left:1rem;right:1rem;font-size:0.65rem;color:rgba(255,255,255,0.4);text-align:center">v2.0 \u2022 法律文档 RAG</div>', unsafe_allow_html=True)

# Token 计数

def _save_feedback(query, answer, rating):
    import json
    fb = {"query": query[:100], "answer": answer[:100], "rating": rating, "timestamp": datetime.now().isoformat()}
    path = "feedback_log.json"
    data = json.loads(open(path, encoding="utf-8").read()) if os.path.exists(path) else []
    data.append(fb)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def count_tokens(text: str) -> int:
    return len(TOKENIZER.encode(text))

# 记忆摘要
def summarize_history(messages: list) -> str:
    if not messages:
        return ""
    history_text = "\n".join([f"{m['role']}: {m['content'][:200]}" for m in messages])
    prompt = f"Summarize the following conversation (50 chars max):\n{history_text}\nSummary:"
    try:
    # 调用 DeepSeek API
        resp = requests.post(
            f"{DEEPSEEK_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"},
            json={"model": "deepseek-chat", "messages": [{"role": "user", "content": prompt}], "temperature": 0.1},
            timeout=15, verify=False,
        )
    # 解析返回
        if resp.status_code == 200:
            data = resp.json()
    # 防御性 JSON 解析
            if isinstance(data, dict) and data.get("choices") and data["choices"][0].get("message"):
                return data["choices"][0]["message"]["content"] or ""
        return ""
    except:
        return ""
# Shadow LLM: for background async tasks (entity extraction, memory consolidation, etc.)
def memory_llm(prompt: str) -> str:
        placeholder.markdown("思考中...")
        # 流式输出: 逐字显示 LLM 回答
        resp = requests.post(
            f"{DEEPSEEK_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": full_prompt}],
                "temperature": 0.1,
                "stream": True,
            },
            timeout=60, verify=False, stream=True,
        )
        if resp.status_code == 200:
            answer = ""
            for chunk in resp.iter_lines():
                if chunk:
                    chunk_str = chunk.decode("utf-8")
                    if chunk_str.startswith("data: "):
                        chunk_data = chunk_str[6:]
                        if chunk_data.strip() == "[DONE]":
                            break
                        try:
                            import json
                            delta = json.loads(chunk_data)["choices"][0]["delta"].get("content", "")
                            if delta:
                                answer += delta
                                placeholder.markdown(answer + "▌")
                        except Exception:
                            pass
            output_tokens = count_tokens(answer)
            total = input_tokens + output_tokens
            st.session_state.last_tokens = total
            st.session_state.total_tokens += total
            placeholder.markdown(answer + f"\n\n---\n*Token: {input_tokens} in + {output_tokens} out = {total}*")
            st.session_state.messages.append({"role": "assistant", "content": answer})
            st.session_state.memory.add("assistant", answer)
            try:
                if "memory" in st.session_state:
                    def memory_llm(p):
                        try:
                            r = requests.post(f"{DEEPSEEK_BASE_URL}/chat/completions",
                                headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"},
                                json={"model": "deepseek-chat", "messages": [{"role": "user", "content": p}], "temperature": 0.1},
                                timeout=15, verify=False)
                            return r.json()["choices"][0]["message"]["content"] if r.status_code == 200 else ""
                        except: return ""
                    st.session_state.memory.async_consolidate(memory_llm)
            except Exception:
                pass
        else:
            placeholder.error(f"API 错误: {resp.status_code}")
        return ""


st.markdown('<div class="main-title"><h1>法律文档问答</h1><span class="badge">v2.0</span></div>', unsafe_allow_html=True)

# 对话历史
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])

if uploaded_file:
    if "embedder" not in st.session_state:
        from langchain_huggingface import HuggingFaceEmbeddings
        st.session_state.embedder = HuggingFaceEmbeddings(
            model_name="shibing624/text2vec-base-chinese",
            cache_folder="./model_cache"
        )
        st.session_state.memory = MemorySystem(
            st.session_state.embedder, "./memory_db", tenant_id=st.session_state.tenant_id
        )
if "vector_store" not in st.session_state:
        if uploaded_file is None:
            st.markdown('''
<div class=welcome-card>
    <div class=icon>📄</div>
    <h2>Get Started</h2>
    <p>Upload a legal document to begin intelligent Q&A with AI-powered retrieval.</p>
    <ul class=steps>
        <li>Upload a PDF document via the sidebar</li>
        <li>Ask questions about the document content</li>
        <li>Get precise answers with source citations</li>
    </ul>
</div>
''', unsafe_allow_html=True)
            st.stop()
        with st.spinner("Parsing PDF with multimodal pipeline..."):
            import tempfile
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                tmp.write(uploaded_file.read())
                tmp_path = tmp.name
            pipeline = MultimodalPipeline()
            multimodal_chunks = pipeline.process(tmp_path)
            os.unlink(tmp_path)
            if not multimodal_chunks:
                st.error("无法提取文本")
                st.stop()
            chunks = [mc.text for mc in multimodal_chunks]
        with st.spinner("Building vector store..."):
            from langchain_community.vectorstores import Chroma
            from langchain_huggingface import HuggingFaceEmbeddings
            embed = HuggingFaceEmbeddings(model_name="shibing624/text2vec-base-chinese", cache_folder="./model_cache")
            st.session_state.vector_store = Chroma.from_texts(
                texts=chunks, embedding=embed,
                metadatas=[{"source": f"{uploaded_file.name} - chunk {i+1}"} for i in range(len(chunks))],
            )
            st.session_state.chunks = chunks
            from app.retrieval.hybrid_retriever import HybridRetriever
            st.session_state.retriever = HybridRetriever(
                dense_store=st.session_state.vector_store,
                texts=chunks,
                k=3,
                use_reranker=False,
            )
        st.markdown('<div style="background:#e8f5e9;border:1px solid #c8e6c9;border-radius:8px;padding:0.8rem 1rem;color:#2e7d32;font-size:0.9rem;text-align:center;max-width:400px;margin:1rem auto">\u2705 文档已就绪，请在下方提问。</div>', unsafe_allow_html=True)

# 用户输入
if prompt := st.chat_input("输入法律问题..."):
    # 输入长度限制
    if len(prompt) > 2000:
        st.error("输入过长（最多2000字符）")
        st.stop()
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.session_state.memory.add("user", prompt)
    with st.chat_message("user"):
        st.write(prompt)
    with st.chat_message("assistant"):
        placeholder = st.empty()
        placeholder.markdown("Thinking...")
        trace = TraceContext()
        trace.set_input(prompt)
        
        trace.begin_span("query_rewrite")
        rewriter = QueryRewriter(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)
        variants = rewriter.rewrite(prompt, num_variants=1)
        search_query = variants[0] if variants else prompt
        trace.end_span()

        docs = st.session_state.get("retriever")
        context = ""
        citations_section = ""
        if docs:
            trace.begin_span("retrieve")
            docs_result = docs.invoke(search_query)
            trace.end_span()
            if docs_result:
                seen = set()
                unique = []
                for d in docs_result:
                    key = d.page_content.strip()[:60]
                    if key not in seen:
                        seen.add(key)
                        unique.append(d)
                docs_result = unique
                citation_tracker = CitationTracker()
                citation_tracker.add_sources(docs_result)
                context = citation_tracker.format_context()
                citations_section = citation_tracker.format_citations()
                profile_text = st.session_state.memory.profile.to_prompt_text(st.session_state.tenant_id)
        history = st.session_state.summary
        if history:
            history = "History: " + history + "\n\n"
        recent = st.session_state.messages[-6:-1]
        if recent:
            history += "\n".join([f"{m['role']}: {m['content'][:200]}" for m in recent]) + "\n\n"
    # 构建 Prompt
        full_prompt = f"""You are a legal expert. Answer based on the provided text.

{history}Reference text:
{context}

Question: {prompt}

Requirements: Cite relevant clauses using [source:N] notation. If the text doesn't contain the answer, state that clearly.

{profile_text}\n\n{citations_section}"""
    # 构建 Prompt
        input_tokens = count_tokens(full_prompt)
        import time as _time
        _query_start = _time.time()
        cached_answer = query_cache.get(full_prompt)
        if cached_answer:
            output_tokens = count_tokens(cached_answer)
            total = input_tokens + output_tokens
            st.session_state.last_tokens = total
            st.session_state.total_tokens += total
            trace.set_tokens(total)
            trace.end_span()
            trace.print_summary()
            get_trace_store().save(trace)
            placeholder.markdown(cached_answer + f"\n\n---\n*Token: {input_tokens} in + {output_tokens} out = {total} (cached)*")
            fb_key = "fb_" + str(len(st.session_state.messages))
            c1, c2 = st.columns([1, 1])
            with c1:
                if st.button("👍 有用", key=fb_key + "_up"):
                    _save_feedback(prompt, cached_answer, "up")
                    st.toast("✅ 感谢反馈！")
            with c2:
                if st.button("👎 没用", key=fb_key + "_down"):
                    _save_feedback(prompt, cached_answer, "down")
                    st.toast("✅ 感谢反馈！")
            st.session_state.messages.append({"role": "assistant", "content": cached_answer})
            st.session_state.memory.add("assistant", cached_answer)
            st.session_state.memory.extract_entities(prompt, cached_answer, memory_llm)
            latency_ms = int((_time.time() - _query_start) * 1000)
            logger.info("query", question=prompt, answer_len=len(cached_answer), tokens=total, latency_ms=latency_ms, cache_hit=True)
            conv_id = conversation_store.save(st.session_state.messages, conv_id=getattr(st.session_state, "conv_id", None))
            st.session_state.conv_id = conv_id
            st.stop()

        try:
    # 调用 DeepSeek API
            resp = requests.post(
                f"{DEEPSEEK_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"},
    # 构建 Prompt
                json={"model": "deepseek-chat", "messages": [{"role": "user", "content": full_prompt}], "temperature": 0.1},
                timeout=60, verify=False,
            )
    # 解析返回
            if resp.status_code == 200:
                data = resp.json()
                answer = "Unexpected response format"
    # 防御性 JSON 解析
                if isinstance(data, dict) and data.get("choices") and data["choices"][0].get("message"):
                    answer = data["choices"][0]["message"]["content"] or "Empty response"
                output_tokens = count_tokens(answer)
                total = input_tokens + output_tokens
                st.session_state.last_tokens = total
                st.session_state.total_tokens += total
                trace.set_output(answer)
                trace.set_tokens(total)
                trace.end_span()
                trace.print_summary()
                get_trace_store().save(trace)
                # 生产集成：缓存 + 日志 + 对话持久化
                query_cache.set(full_prompt, answer)
                latency_ms = int((_time.time() - _query_start) * 1000)
                logger.info("query", question=prompt, answer_len=len(answer), tokens=total, latency_ms=latency_ms, cache_hit=False)
                conv_id = conversation_store.save(st.session_state.messages, conv_id=getattr(st.session_state, "conv_id", None))
                st.session_state.conv_id = conv_id
                placeholder.markdown(answer + f"\n\n---\n*Token: {input_tokens} in + {output_tokens} out = {total}*")
                # 用户反馈
                fb_key = f"fb_{len(st.session_state.messages)}"
                c1, c2 = st.columns([1, 1])
                with c1:
                    if st.button("\U0001f44d \u6709\u7528", key=f"{fb_key}_up"):
                        _save_feedback(prompt, answer, "up")
                        st.toast("\u2705 \u611f\u8c22\u53cd\u9988\uff01")
                with c2:
                    if st.button("\U0001f44e \u6ca1\u7528", key=f"{fb_key}_down"):
                        _save_feedback(prompt, answer, "down")
                        st.toast("\u2705 \u611f\u8c22\u53cd\u9988\uff01")
                st.session_state.messages.append({"role": "assistant", "content": answer})
                st.session_state.memory.add("assistant", answer)
                # 影子提取：后台异步更新用户画像（不阻塞对话）
                st.session_state.memory.extract_entities(prompt, answer, memory_llm)
                if len(st.session_state.messages) >= 8:
                    old = st.session_state.messages[:-6]
                    new_summary = summarize_history(old)
                    if new_summary:
                        st.session_state.summary = new_summary
            else:
                placeholder.error(f"API error: {resp.status_code}")
        except Exception as e:
            placeholder.error(f"错误: {e}")
    # 刷新页面
    st.rerun()
