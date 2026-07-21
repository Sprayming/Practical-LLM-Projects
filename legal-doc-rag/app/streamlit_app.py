
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
from app.processing.multimodal_pipeline import MultimodalPipeline
from openai import OpenAI

class DirectEmbed:
    def __init__(self, api_key, base_url, model):
        self._client = OpenAI(api_key=api_key, base_url=base_url)
        self._model = model
    def embed_documents(self, texts):
        resp = self._client.embeddings.create(input=texts, model=self._model)
        return [d.embedding for d in resp.data]
    def embed_query(self, text):
        resp = self._client.embeddings.create(input=text, model=self._model)
        return resp.data[0].embedding
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
if "uploaded_docs" not in st.session_state:
    st.session_state.uploaded_docs = []
if "tenant_id" not in st.session_state:
    st.session_state.tenant_id = "default"

# 页面设置
st.set_page_config(page_title="Legal Document RAG", layout="wide")
st.markdown("""<style>.stApp {background:#f5f5f5;} .stChatMessage {background:white;border-radius:8px;padding:12px;margin:8px 0;box-shadow:0 1px 3px rgba(0,0,0,0.1);} .stChatFade {display:none;} h1,h2,h3 {color:#1a237e!important;} section[data-testid="stSidebar"] {width:320px!important;} .stButton button {background:#1a237e;color:white;border-radius:6px;} </style>""", unsafe_allow_html=True)

# 侧边栏
with st.sidebar:
    st.header("法律文书 RAG 系统")
    tenant_id = st.text_input("租户 ID", value=st.session_state.tenant_id, key="tenant_input")
    if tenant_id != st.session_state.tenant_id:
        st.session_state.tenant_id = tenant_id
        st.session_state.messages = []
        st.session_state.summary = ""
        st.session_state.total_tokens = 0
        st.rerun()
    uploaded_file = st.file_uploader("上传 PDF 文件", type="pdf")
    st.divider()
    st.subheader("Token 统计")
    col1, col2 = st.columns(2)
    col1.metric("当前", st.session_state.get("last_tokens", 0))
    col2.metric("总计", st.session_state.total_tokens)
    if st.button("清除历史"):
        st.session_state.messages = []
        st.session_state.summary = ""
        st.session_state.total_tokens = 0
    # 刷新页面
        st.rerun()
    st.caption("会话轮数: " + str(len(st.session_state.messages) // 2))

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


st.title("法律文书智能问答")

# 对话历史
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])
        if msg["role"] == "assistant" and msg.get("citations"):
            with st.expander("????", expanded=False):
                st.markdown(msg["citations"])

if uploaded_file:
    if "embedder" not in st.session_state:
        st.session_state.embedder = DirectEmbed("df9c9b2d-35d9-4df6-b49d-f489708e1eab", "https://ark.cn-beijing.volces.com/api/v3/", "ep-m-20251117205847-trwgz")
        st.session_state.memory = MemorySystem(
            st.session_state.embedder, "./memory_db", tenant_id=st.session_state.tenant_id
        )
if "vector_store" not in st.session_state:
        if uploaded_file is None:
            st.info("请先上传一份 PDF 文件")
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
                st.error("无法提取文本，请检查 PDF")
                st.stop()
            chunks = [mc.text for mc in multimodal_chunks]
            if uploaded_file.name not in st.session_state.uploaded_docs:
                st.session_state.uploaded_docs.append(uploaded_file.name)
        with st.spinner("Building vector store..."):
            embed = DirectEmbed("df9c9b2d-35d9-4df6-b49d-f489708e1eab", "https://ark.cn-beijing.volces.com/api/v3/", "ep-m-20251117205847-trwgz")
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
        st.success("准备就绪，请在下方提问")

# 用户输入
if prompt := st.chat_input("请输入你的法律问题..."):
    # 输入长度限制
    if len(prompt) > 2000:
        st.error("输入过长（最大 2000 字符）")
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
        st.session_state.profile_text = profile_text
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
