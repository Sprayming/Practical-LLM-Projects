
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
from langchain_community.vectorstores import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from app.retrieval.hybrid_retriever import HybridRetriever
from app.retrieval.citation import CitationTracker
from app.retrieval.query_rewriter import QueryRewriter
from app.observability.tracker import TraceContext, get_trace_store
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
st.set_page_config(page_title="Legal Document RAG", layout="wide")
# 生产环境认证（可选, 通过 APP_PASSWORD 环境变量开启）
APP_PASSWORD = os.getenv("APP_PASSWORD", "")
if APP_PASSWORD:
    if not st.session_state.get("authenticated"):
        st.title("Legal Document RAG")
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
    st.header("Legal Document RAG")
    tenant_id = st.text_input("Tenant ID", value=st.session_state.tenant_id, key="tenant_input")
    if tenant_id != st.session_state.tenant_id:
        st.session_state.tenant_id = tenant_id
        st.session_state.messages = []
        st.session_state.summary = ""
        st.session_state.total_tokens = 0
        st.rerun()
    uploaded_file = st.file_uploader("Upload PDF", type="pdf")
    st.divider()
    st.subheader("Token Stats")
    col1, col2 = st.columns(2)
    col1.metric("Current", st.session_state.get("last_tokens", 0))
    col2.metric("Total", st.session_state.total_tokens)
    if st.button("Clear History"):
        st.session_state.messages = []
        st.session_state.summary = ""
        st.session_state.total_tokens = 0
    # 刷新页面
        st.rerun()
    st.caption("Rounds: " + str(len(st.session_state.messages) // 2))

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
        placeholder.markdown("Thinking...")
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
            placeholder.error(f"API error: {resp.status_code}")
        return ""


st.title("Legal Document Q&A")

# 对话历史
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])

if uploaded_file:
    if "embedder" not in st.session_state:
        st.session_state.embedder = HuggingFaceEmbeddings(
            model_name="shibing624/text2vec-base-chinese",
            cache_folder="./model_cache"
        )
        st.session_state.memory = MemorySystem(
            st.session_state.embedder, "./memory_db", tenant_id=st.session_state.tenant_id
        )
if "vector_store" not in st.session_state:
        if uploaded_file is None:
            st.info("Please upload a PDF file to begin")
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
                st.error("No text could be extracted")
                st.stop()
            chunks = [mc.text for mc in multimodal_chunks]
        with st.spinner("Building vector store..."):
            embed = HuggingFaceEmbeddings(model_name="shibing624/text2vec-base-chinese", cache_folder="./model_cache")
            st.session_state.vector_store = Chroma.from_texts(
                texts=chunks, embedding=embed,
                metadatas=[{"source": f"{uploaded_file.name} - chunk {i+1}"} for i in range(len(chunks))],
            )
            st.session_state.chunks = chunks
            st.session_state.retriever = HybridRetriever(
                dense_store=st.session_state.vector_store,
                texts=chunks,
                k=3,
                use_reranker=False,
            )
        st.success("Ready. Ask your question below.")

# 用户输入
if prompt := st.chat_input("Ask a legal question:"):
    # 输入长度限制
    if len(prompt) > 2000:
        st.error("Input too long (max 2000 chars)")
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
            placeholder.error(f"Error: {e}")
    # 刷新页面
    st.rerun()
