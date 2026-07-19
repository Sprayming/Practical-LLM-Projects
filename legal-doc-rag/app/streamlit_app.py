
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
from PyPDF2 import PdfReader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from app.retrieval.hybrid_retriever import HybridRetriever
from app.retrieval.citation import CitationTracker
from app.retrieval.query_rewriter import QueryRewriter
from app.observability.tracker import TraceContext, get_trace_store

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

# 页面设置
st.set_page_config(page_title="Legal Document RAG", layout="wide")

# 侧边栏
with st.sidebar:
    st.header("Legal Document RAG")
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
    try:
        resp = requests.post(
            f"{DEEPSEEK_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"},
            json={"model": "deepseek-chat", "messages": [{"role": "user", "content": prompt}], "temperature": 0.1},
            timeout=15, verify=False,
        )
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, dict) and data.get("choices") and data["choices"][0].get("message"):
                return data["choices"][0]["message"]["content"] or ""
        return ""
    except:
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
            st.session_state.embedder, "./memory_db"
        )
if "vector_store" not in st.session_state:
        if uploaded_file is None:
            st.info("Please upload a PDF file to begin")
            st.stop()
        with st.spinner("Parsing PDF..."):
            reader = PdfReader(uploaded_file)
            text = "\n".join([(page.extract_text() or "") for page in reader.pages])
            if not text.strip():
                st.error("No text could be extracted")
                st.stop()
        with st.spinner("Chunking text..."):
            splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50, separators=["\n\n", "\n", ".", "。"])
            chunks = splitter.split_text(text)
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

{citations_section}"""
    # 构建 Prompt
        input_tokens = count_tokens(full_prompt)
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
                placeholder.markdown(answer + f"\n\n---\n*Token: {input_tokens} in + {output_tokens} out = {total}*")
                st.session_state.messages.append({"role": "assistant", "content": answer})
                st.session_state.memory.add("assistant", answer)
                # 影子提取：后台异步更新用户画像（不阻塞对话）
    # 影子提取：异步更新画像
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
