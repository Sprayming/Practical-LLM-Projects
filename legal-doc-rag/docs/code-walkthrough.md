# legal-doc-rag · 代码级逐函数详解（能凭自己写出来版）
> 最后更新：2026-08-08 用户要求"把代码直接贴出来讲解"，已在对话中完成双链路逐函数讲解。
> 覆盖：main.py 骨架 / documents.py 上传 / middleware 安全三件套 / multimodal_pipeline 切块 /
> embedder_factory 向量化 / auth 鉴权 / chat 七步问答 / query_rewriter 改写 /
> hybrid_retriever 混合检索(RRF+BGE) / citation 引用追踪 / 流式输出。

> 配套 `student.md`（第七节 SVG 图 + 第八节代码直读 + 第九节函数映射）与 `docs/architecture-explainer.html`（带语音讲解视频）。
> 本文档**逐函数贴真实源码 + 行内注释**，目标是：合上仓库也能把每个函数的内部逻辑默写出来。
> 所有代码均来自当前 `main` 分支，行号见各函数标注。

---

## 0. 阅读顺序建议

```
入口（路由）            → 业务函数（retrieval/processing/memory/security/tenant） → 持久层（Chroma/SQLite/磁盘）
documents.py / chat.py      hybrid_retriever / multimodal_pipeline / citation        chroma_db / uploads / memory_db
        │                              │                                                  │
        └── 鉴权：auth.py:require_user ┘                                                  └── 按 tenant_id 子目录隔离
```

---

## 一、上传入库链路（逐函数）

### 1.1 入口 `app/api/documents.py:20` `upload_document()`

```python
@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    user: dict = Depends(require_user),     # ← 每个请求先过鉴权，拿到 user["tenant_id"]
):
    tenant_id = user["tenant_id"]

    # ① 扩展名白名单，只允许 .pdf
    if not file.filename:
        raise HTTPException(400, "No filename provided")
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:        # ALLOWED_EXTENSIONS = {".pdf"}
        raise HTTPException(400, f"File type not allowed...")

    # ② 读字节 + 100MB 上限
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:         # MAX_FILE_SIZE = 100*1024*1024
        raise HTTPException(413, f"File too large...")

    # ③ 拼「安全」落盘路径（防路径穿越，见 1.2）
    file_path = get_safe_upload_path(cfg.UPLOAD_DIR, tenant_id, file.filename)

    with open(file_path, "wb") as f:
        f.write(content)                      # ← PDF 原始文件落到 uploads/<tenant_id>/

    # ④ 切块
    pipeline = MultimodalPipeline()
    chunks = pipeline.process(file_path)     # → List[MultimodalChunk]
    if not chunks:
        raise HTTPException(400, "No text extracted from PDF")

    # ⑤ 取纯文本 + 建 embedder
    texts = [c.text for c in chunks]         # 每个 chunk 的纯文本
    embedder = create_embedder()             # 见 1.4

    # ⑥ 落向量库：persist_directory 直接带 tenant_id → 物理隔离
    persist_dir = os.path.join(cfg.CHROMA_PERSIST_DIR, tenant_id)
    vector_store = Chroma.from_texts(
        texts=texts,
        embedding=embedder,
        metadatas=[{"source": file.filename, "chunk": i} for i in range(len(texts))],
        persist_directory=persist_dir,
    )
    vector_store.persist()                   # ← 写入 chroma_db/<tenant_id>/ 磁盘

    return {"success": True, "filename": file.filename, "chunks": len(texts), "tenant_id": tenant_id}
```

**逐行要点**
- `Depends(require_user)` 是 FastAPI 依赖注入：请求进函数前先跑 `auth.py` 的 `require_user()`，把 HTTP 头里的 JWT 解成 `user` dict（含 `tenant_id`）。**这就是租户隔离的起点**。
- 第 ③ 步 `get_safe_upload_path` 不是简单拼接，它做了 `tenant_id` 清洗 + 文件名清洗 + 路径穿越校验（见 1.2）。
- 第 ⑥ 步是隔离的关键：`persist_directory = chroma_db/<tenant_id>`，每个租户一个独立 Chroma 库，**不是 collection 字段隔离**。
- `metadatas` 里写 `"source": file.filename`，查询时删除/引用都靠这个字段回查。

### 1.2 安全护栏 `app/security/middleware.py`

```python
# ① tenant_id 清洗：只留字母数字下划线，杜绝注入路径分隔符
def get_safe_upload_path(upload_dir: str, tenant_id: str, filename: str) -> str:
    safe_tenant = re.sub(r'[^a-zA-Z0-9_-]', '', tenant_id)   # 任何非白名单字符一律删掉
    safe_filename = sanitize_filename(filename)
    upload_dir = os.path.join(upload_dir, safe_tenant)
    os.makedirs(upload_dir, exist_ok=True)
    file_path = os.path.join(upload_dir, safe_filename)
    if not is_safe_path(upload_dir, file_path):              # ② 终极校验
        raise ValueError(f"Unsafe file path detected: {filename}")
    return file_path
```

```python
# 文件名清洗：去空字节、去路径分隔、去前导点、替换非法字符、限长 255
def sanitize_filename(filename: str) -> str:
    if not filename:
        return "unnamed"
    filename = filename.replace("\x00", "")        # 去空字节
    filename = os.path.basename(filename)           # 只保留文件名，丢掉任何目录前缀
    filename = filename.lstrip(".")                # 去前导点（防 Unix 隐藏文件）
    filename = re.sub(r'[<>:"|?*]', '_', filename) # 替换 Windows 非法字符
    if len(filename) > 255:                        # 限长
        name, ext = os.path.splitext(filename)
        filename = name[:255 - len(ext)] + ext
    return filename or "unnamed"
```

```python
# 路径穿越终极防线：解析真实绝对路径后判断是否在 base 内
def is_safe_path(base_dir: str, target_path: str) -> bool:
    try:
        base = Path(base_dir).resolve()            # 解析符号链接、.. 等到真实绝对路径
        target = Path(target_path).resolve()
        return target.is_relative_to(base)         # Python 3.9+：target 必须仍在 base 之下
    except (ValueError, OSError):
        return False
```

**为什么这三层缺一不可**
- 只拼路径不加租户清洗 → 攻击者在 `tenant_id` 里塞 `../../etc` 就可能写到别处。
- 只在 `tenant_id` 清洗 → 文件名 `../../secret.pdf` 仍能穿越，所以要 `sanitize_filename` + `basename`。
- 前两步都做了还不够稳健 → `is_safe_path` 用 `resolve()` 后做"是否仍在 base 内"的兜底断言，是最后一道闸。

> 删除文档 `documents.py:108 delete_document()` 也用同样三件套（`sanitize_filename` + `is_safe_path`），并用 `vector_store.get(where={"source": filename})` 取出 ids 再 `delete` + `persist()`。

### 1.3 切块 `app/processing/multimodal_pipeline.py:29` `process()`

```python
class MultimodalPipeline:
    def __init__(self):
        self._ocr = OCREngine()
        # 递归字符切分器：块 500 字，重叠 50 字；中英文断点
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=500, chunk_overlap=50,
            separators=["\n\n", "\n", "。", "；", "，", " "],
        )

    def process(self, file_path: str) -> list[MultimodalChunk]:
        ext = Path(file_path).suffix.lower()
        if ext == ".pdf":
            return self._process_pdf(file_path)
        else:
            text = Path(file_path).read_text(encoding="utf-8")
            return [MultimodalChunk(text=text, page_number=1)]
```

```python
    def _process_pdf(self, pdf_path: str) -> list[MultimodalChunk]:
        pages = extract_pdf_pages(pdf_path)        # 抽每页：{"text", "images", "page_number"}
        chunks = []
        for page in pages:
            page_text = page["text"]
            page_images = page["images"]
            ocr_texts = []
            for img in page_images:                # ① 图片 OCR 出文字
                ocr_result = self._ocr.recognize(img["bytes"])
                if ocr_result:
                    ocr_texts.append(ocr_result)
            caption_texts = []
            try:                                   # ② 图片用视觉模型生成描述
                captioner = VisionCaptioner(api_key=cfg.LLM_API_KEY, base_url=cfg.LLM_BASE_URL)
                for img in page_images:
                    caption = captioner.caption(img["bytes"], img.get("ext", "png"))
                    if caption:
                        caption_texts.append("[图片描述] " + caption)
            except Exception:
                pass
            # ③ 合并：原文本 + 图片描述 + OCR 文字
            combined = page_text
            if caption_texts:
                combined += "\n" + "\n".join(caption_texts)
            if ocr_texts:
                combined += "\n[图片文字]\n" + "\n".join(ocr_texts)
            if not combined.strip():
                continue
            # ④ 切分成 500 字左右的块
            split_texts = self._splitter.split_text(combined)
            for st in split_texts:
                chunks.append(MultimodalChunk(text=st, page_number=page["page_number"], images=...))
        return chunks
```

**逐行要点**
- 这是"多模态"的含义：**文本 + OCR 文字 + 图片描述** 三种信号合并成一个文本块再切块。
- 图片本身不被向量化，被转成文字后进入 `text`，所以本质仍是文本 RAG（图片信息靠 OCR/Vision 描述保留）。
- `chunk_size=500` 是经验值：太大召回不精准，太小丢上下文。

### 1.4 向量化 `app/retrieval/embedder_factory.py:35` `create_embedder()`

```python
class DirectEmbed:
    def __init__(self, model, api_key, base_url):
        self.model = model; self.api_key = api_key; self.base_url = base_url.rstrip("/")

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        resp = requests.post(
            f"{self.base_url}/embeddings",                  # 直接打 embedding 接口
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json={"model": self.model, "input": texts},     # 批量传文本
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()
        # 按 index 排序后取 embedding（保证与输入顺序一致）
        return [item["embedding"] for item in sorted(data["data"], key=lambda x: x["index"])]

    def embed_query(self, text: str) -> List[float]:
        return self.embed_documents([text])[0]

def create_embedder():
    embedder_type = os.getenv("EMBEDDER_TYPE", "openai")
    if embedder_type == "openai":
        return DirectEmbed(
            model=os.getenv("EMBEDDING_MODEL", "ep-m-20251117205847-trwgz"),
            api_key=os.getenv("EMBEDDING_API_KEY", ""),
            base_url=os.getenv("EMBEDDING_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3"),
        )
    elif embedder_type == "huggingface":
        from langchain_huggingface import HuggingFaceEmbeddings
        return HuggingFaceEmbeddings(model_name=os.getenv("HF_MODEL_NAME", "BAAI/bge-m3"), ...)
    else:
        raise ValueError(f"Unknown embedder_type: {embedder_type}")
```

**逐行要点**
- 默认走 **OpenAI 兼容接口**（这里接的是火山方舟 `ark.cn-beijing.volces.com`）。
- `sorted(data["data"], key=lambda x: x["index"])` 很关键：批量 embedding 返回顺序未必和输入一致，必须按 `index` 排回来，否则"文本↔向量"错位。
- 可插拔：`EMBEDDER_TYPE=huggingface` 时本地跑 `BAAI/bge-m3`，不依赖外部 API。

### 1.5 持久化后磁盘上长什么样

```
chroma_db/
  └── <tenant_id>/
        ├── chroma.sqlite3        # 元数据 + 集合信息
        └── <uuid>/               # 向量索引分片
              ├── data_level0.bin
              └── header.bin
uploads/
  └── <tenant_id>/
        └── 合同A.pdf             # 原始 PDF
```

> `Chroma.from_texts(...).persist()` 就是把上面的目录写进磁盘；查询时 `Chroma(persist_directory=...)` 重新加载。

---

## 二、查询问答链路（逐函数）

### 2.1 入口 `app/api/chat.py:179` `chat()`

```python
@router.post("")
@limiter.limit("100/minute")                                   # 限流：每分 100 次
async def chat(request: Request, req: ChatRequest, user: dict = Depends(require_user)):
    embedder, vector_store, qr, cache, ct = _build_pipeline(user["tenant_id"])   # 见 2.2
    mem = _get_memory(user["tenant_id"], embedder) if embedder else None

    # 1. 没建库直接返回提示
    if vector_store is None:
        return JSONResponse(content={"answer": "请先上传文档", "citations": [], "token_usage": 0})

    # 2. 查询改写（LLM 把问题改得更利于检索）
    queries = qr.rewrite(req.message, num_variants=1) if qr else [req.message]
    query = queries[0] if queries else req.message

    # 3. 记忆上下文 + 缓存
    mem_ctx = mem.get_context(query) if mem else ""
    cached = cache.get(query) if cache else None

    # 4. 命中缓存：直接返回（流式/非流式）
    if cached:
        content = cached if isinstance(cached, str) else cached.get("answer", str(cached))
        if req.stream:
            async def _cached_stream():
                yield f"data: {json.dumps({'type': 'token', 'content': content})}\n\n"
                yield f"data: {json.dumps({'type': 'done', 'citations': [], 'token_usage': 0})}\n\n"
            return StreamingResponse(_cached_stream(), media_type="text/event-stream")
        else:
            return JSONResponse(content={"answer": content, "citations": [], "token_usage": 0})

    # 5. RAG 检索
    all_texts = []
    try:
        all_data = vector_store._collection.get()              # 取出全部文本，喂给 BM25
        all_texts = all_data.get("documents", []) or []
    except Exception:
        pass

    retriever = HybridRetriever(vector_store, all_texts, k=10) # 见 2.4
    docs = retriever.retrieve(query)                          # 混合检索
    docs = _get_reranker().rerank(query, docs, top_k=5)       # 见 2.5 精排
    ct.add_sources(docs)                                      # 记录来源
    context = ct.format_context()                             # 拼成 [1] 文件名\n内容 形式

    # 6. 拼 Prompt
    history_text = ""
    for m in (req.history or [])[-4:]:                        # 只取最近 4 轮历史
        history_text += f"{m.get('role','user')}: {m.get('content','')[:200]} " + chr(10)
    PROMPT_TEMPLATE = """你是一个法律专家助手。回答基于提供的文本。
    参考文本:
    {context}
    记忆上下文:
    {memory}
    对话历史:
    {history}
    问题: {question}
    要求: 使用 [N] 引用相关文本片段。如果文本不包含答案，请明确说明。"""
    prompt = PROMPT_TEMPLATE.format(context=context, memory=mem_ctx, history=history_text, question=query)

    # 7. 流式 / 非流式分流（见 2.7 / 2.8）
    if req.stream:
        return StreamingResponse(generate(), media_type="text/event-stream")
    else:
        ... # 非流式：直接 httpx.post 拿完整 answer
```

**逐行要点**
- `_build_pipeline` 失败、`vector_store is None`（租户还没上传）→ 直接"请先上传文档"，是优雅降级。
- `qr.rewrite` 是**可选增强**：LLM 把"劳动合同法辞职赔偿"改写成"解除劳动合同 经济补偿 赔偿金 N+1"之类，提升召回。
- `vector_store._collection.get()` 取**全量文本**给 BM25 建稀疏索引——这是 hybrid 的"稀疏"那一路。
- `k=10` 先召回收窄到 10，`top_k=5` 再精排到 5。

### 2.2 装配管道 `app/api/chat.py:162` `_build_pipeline()`

```python
def _build_pipeline(tenant_id: str):
    try:
        embedder = create_embedder()
        persist_dir = os.path.join(cfg.CHROMA_PERSIST_DIR, tenant_id)   # 按租户读回
        if not os.path.exists(persist_dir):
            return None, None, None, None, None                         # 没建库 → 全 None
        vector_store = Chroma(embedding_function=embedder, persist_directory=persist_dir)
        query_rewriter = QueryRewriter(api_key=cfg.LLM_API_KEY, base_url=cfg.LLM_BASE_URL)
        cache = QueryCache(cache_dir=os.path.join("cache", tenant_id))
        citation_tracker = CitationTracker()
        return embedder, vector_store, query_rewriter, cache, citation_tracker
    except Exception as e:
        _log.error(f"管道构建失败: {str(e)}")
        return None, None, None, None, None
```

**要点**：与上传端**完全对称**——用同一个 `chroma_db/<tenant_id>` 读回向量库。其余三个都是轻量对象：`QueryRewriter`（改写）、`QueryCache`（查缓存）、`CitationTracker`（管引用）。

### 2.3 查询改写 `app/retrieval/query_rewriter.py:29` `rewrite()`

```python
def rewrite(self, query: str, context: str = "", num_variants: int = 2) -> list[str]:
    if not self.api_key:
        return [query]                                              # 没 key 就原样返回（降级）
    prompt = f"""你是一个法律检索专家。请将用户的问题改写成更适合向量检索的形式。
原问题：{query}
要求：1.保持原意 2.补充法律术语 3.多子问题拆独立查询 4.每变体≤50字
输出格式（JSON 数组）：["改写后的查询1", "改写后的查询2"] 只输出 JSON。"""
    try:
        resp = requests.post(f"{self.base_url}/chat/completions", ...json={"model":"deepseek-chat", ...})
        if resp.status_code == 200:
            content = resp.json()["choices"][0]["message"]["content"]
            variants = json.loads(content.strip())                  # 解析 JSON 数组
            if isinstance(variants, list) and len(variants) > 0:
                all_queries = [query] + [v for v in variants if v.strip() != query]  # 去重+保原句
                return all_queries[:num_variants + 1]
    except Exception as e:
        logger.warning("Query rewrite failed: {}", e)
    return [query]                                                 # 任何失败都回退原查询
```

**要点**：核心是"**失败即回退原查询**"——重写是锦上添花，绝不能因为 LLM 挂了就让整个问答挂掉。

### 2.4 混合检索 `app/retrieval/hybrid_retriever.py:238` `retrieve()`

```python
def retrieve(self, query: str, top_k: Optional[int] = None) -> list[Document]:
    k = top_k or self.k
    dense = self._dense_search(query)                 # ① 稠密（向量语义）
    sparse = self._sparse_search(query)               # ② 稀疏（BM25 关键词）
    elasticsearch_results = self._elasticsearch_search(query)   # ③ 可选 ES 全文
    fused = self._rrf_fuse(dense, sparse, elasticsearch_results) # ④ RRF 融合
    if self.reranker and self.reranker.available:     # ⑤ 精排（类内自带，chat 端先用全局 _reranker）
        fused = self.reranker.rerank(query, fused, k)
    else:
        fused = fused[:k]
    return fused
```

**三路子函数**

```python
# ① 稠密：Chroma 相似度搜索，k*3 扩大召回
def _dense_search(self, query):
    results = self.dense_store.similarity_search_with_score(query, k=self.k * 3)
    # Chroma 返回的是距离，0=最近；转成 similarity = 1 - score/2
    return [(doc, 1.0 - score / 2.0) for doc, score in results]
```

```python
# ② 稀疏：BM25 关键词。先对自己构造时传入的 all_texts 做 tokenize 建索引
def _sparse_search(self, query):
    tokenized = self._tokenize(query)                 # 中英文分词 + 去停用词 + 中文 bigram
    scores = self.bm25.get_scores(tokenized)
    scored = [(i, scores[i]) for i in range(len(scores)) if scores[i] > 0]
    scored.sort(key=lambda x: x[1], reverse=True)
    return [(self.texts[i], s) for i, s in scored[:self.k * 3]]
```

```python
# ④ RRF 融合：Reciprocal Rank Fusion，不依赖原始分数尺度，只靠排名
def _rrf_fuse(self, dense_results, sparse_results, elasticsearch_results=None):
    doc_map = {}
    # 稠密路：第 rank 名的文档，rrf_score += dense_weight / (rrf_k + rank + 1)
    for rank, (doc, score) in enumerate(dense_results):
        key = doc.page_content[:200]
        if key not in doc_map:
            doc_map[key] = doc
            doc_map[key].metadata["rrf_score"] = 0.0
        doc_map[key].metadata["rrf_score"] += self.dense_weight / (self.rrf_k + rank + 1)
    # 稀疏路同理叠加
    for rank, (text, score) in enumerate(sparse_results):
        key = text[:200]
        if key not in doc_map:
            doc_map[key] = Document(page_content=text, metadata={"rrf_score": 0.0})
        doc_map[key].metadata["rrf_score"] += self.sparse_weight / (self.rrf_k + rank + 1)
    # ES 路同理（可选）
    result = sorted(doc_map.values(), key=lambda d: d.metadata["rrf_score"], reverse=True)
    return result
```

**逐行要点**
- **为什么 hybrid 而不纯语义**：法律术语（"N+1""竞业限制"）靠 BM25 精确命中关键词，避免纯向量把"赔偿金"和"补偿金"混淆漏检；向量负责语义相似，BM25 负责字面精确。
- **RRF 公式** `score += weight / (k + rank + 1)`（`rrf_k=60`）：排名第 1 贡献 `1/61`，第 2 名 `1/62`……两路都靠前的文档总分最高。**关键优势是不用归一化两路分数**（向量相似度和 BM25 分值量纲不同，直接相加会失衡）。
- 注意：`HybridRetriever` 构造时 `use_reranker=False`（见 `chat.py:221` 直接 `HybridRetriever(...)` 没传），所以类内 `reranker` 为 `None`，精排实际由 `chat.py:223` 的全局 `_get_reranker().rerank()` 完成（见 2.5）。

### 2.5 精排 `app/retrieval/hybrid_retriever.py:42` `Reranker.rerank()`

```python
class Reranker:
    def __init__(self, model_name: str = "BAAI/bge-reranker-base"):
        self.model = None
        self.available = False
        try:
            from sentence_transformers import CrossEncoder
            self.model = CrossEncoder(model_name, device="cpu")   # 懒加载，CPU 上跑
            self.available = True
        except Exception as e:
            logger.warning("Reranker unavailable (skip): {}", e)   # 加载失败 → 跳过，不崩

    def rerank(self, query: str, documents: list[Document], top_k: int = 5) -> list[Document]:
        if not self.available or not documents:
            return documents[:top_k]                              # 不可用就原样截断
        # Cross-Encoder：query 和 doc 拼成一对，直接输出相关性分数
        pairs = [[query, d.page_content[:512]] for d in documents]
        scores = self.model.predict(pairs)
        scored = list(zip(documents, scores))
        scored.sort(key=lambda x: x[1], reverse=True)             # 按分数降序
        return [d for d, _ in scored[:top_k]]                     # 取前 top_k
```

**逐行要点**
- **Bi-Encoder（检索）vs Cross-Encoder（精排）**：前面 Chroma/BM25 是 Bi-Encoder，query 和 doc 各自编码再算相似，**快但精度低**；BGE-Reranker 是 Cross-Encoder，把 `query+doc` 拼一起过模型，**慢但精度高**，所以只用在召回后的 Top-N 精排，兼顾速度与质量。
- `d.page_content[:512]` 截断避免超长文本撑爆显存。
- `available=False` 时直接 `documents[:top_k]` 降级——又一处"失败不崩"。

### 2.6 引用拼接 `app/retrieval/citation.py:55` `format_context()`

```python
def format_context(self) -> str:
    parts = []
    for i, src in enumerate(self._sources):
        marker = f"[{i + 1}]"                       # [1] [2] ...
        ref = f"{src.filename}"                     # 文件名
        if src.page_number:
            ref += f" 第{src.page_number}页"
        parts.append(f"{marker} {ref}\n{src.content}")   # [1] 合同A.pdf 第3页\n内容...
    return "\n\n".join(parts)
```

**要点**：`[1]`、`[2]` 这些标号就是 Prompt 里"使用 [N] 引用"要求 LLM 对应的标记。LLM 回答里写 `[1]` 就能回指到来源。

### 2.7 流式回答 `app/api/chat.py:260` `generate()`（节选）

```python
async def generate() -> AsyncGenerator[str, None]:
    full_answer = ""
    async with httpx.AsyncClient(timeout=60, verify=True) as client:
        async with client.stream("POST", f"{cfg.LLM_BASE_URL}/chat/completions",
            headers={...},
            json={"model": cfg.LLM_MODEL, "messages":[{"role":"user","content":prompt}],
                  "stream": True, "temperature": 0.1, "max_tokens": 1024}) as resp:
            async for line in resp.aiter_lines():
                if line and line.startswith("data: "):
                    data_str = line[6:]
                    if data_str == "[DONE]": break
                    chunk = json.loads(data_str)
                    token = chunk["choices"][0].get("delta", {}).get("content", "")
                    if token:
                        full_answer += token
                        yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"  # SSE 逐字推
    # 收尾：处理引用/缓存/记忆，最后发 done
    sources = ct.get_sources()
    citations = [{"source": ..., "content": ...} for s in sources]
    yield f"data: {json.dumps({'type': 'done', 'citations': citations, 'token_usage': 0})}\n\n"
```

**要点**：SSE（Server-Sent Events）格式：`data: {json}\n\n` 一行一个事件。前端逐行读 `type: token` 拼字（打字机效果），最后读 `type: done` 拿引用列表。

### 2.8 同步调用 LLM `app/api/chat.py:85` `call_llm()`（被改写/记忆后台任务复用）

```python
async def call_llm(prompt: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=30, verify=True) as client:
            r = await client.post(
                f"{cfg.LLM_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {cfg.LLM_API_KEY}", "Content-Type": "application/json"},
                json={"model": cfg.LLM_MODEL, "messages":[{"role":"user","content":prompt}],
                      "temperature": 0.1, "max_tokens": 512},
            )
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        _log.error(f"LLM 调用未知错误: {str(e)}")
        return ""                              # 失败返回空串，调用方自行降级
```

---

## 三、三层记忆 `app/memory/memory_manager.py`

```python
class MemorySystem:
    def __init__(self, embedding_model, persist_dir="./memory_db", tenant_id="default", ...):
        self.redis = RedisClient(redis_url)                       # 短期/中期存 Redis
        self.store = Chroma(collection_name=f"memory_{tenant_id}",  # 长期存 Chroma（按租户）
                            embedding_function=embedding_model, persist_directory=persist_dir)
        self.short_term: List[Dict] = []                          # 内存兜底
        self.mid_term: str = ""
        self.forgetting = ForgettingMechanism(threshold=0.15)      # 遗忘衰减
        self.worker = get_worker()                                # 后台异步
        self._restore_from_redis()                                # 启动恢复

    def add(self, role, content):                                 # 同步写短期
        self.short_term.append({"role": role, "content": content, "timestamp": ...})
        self.redis.add_short_term(self.session_id, role, content)

    def retrieve_long_term(self, query, k=3, min_score=0.25):     # 同步读长期
        results = self.store.similarity_search_with_score(query, k=k*3)
        for doc, distance in results:
            similarity = max(0.0, 1.0 - distance / 2.0)
            if similarity < min_score: continue                   # 过滤低分
            forgetting_score = self.forgetting.score(...)          # 计算遗忘分
            if not self.forgetting.should_forget(forgetting_score):
                filtered_docs.append(doc)
        return [doc.page_content for doc in filtered_docs[:k]]

    def get_context(self, query) -> str:                          # 组装完整上下文
        parts = []
        long_memories = self.retrieve_long_term(query)
        if long_memories: parts.append("[Related Past]\n" + "\n---\n".join(long_memories))
        mid = self.redis.get_mid_term(self.session_id) or self.mid_term
        if mid: parts.append("[Session Summary]\n" + mid)
        if self.short_term:
            recent = "\n".join([f"{m['role']}: {m['content'][:200]}" for m in self.short_term[-4:]])
            parts.append("[Recent]\n" + recent)
        return "\n\n".join(parts)

    def trigger_background_jobs(self, llm_func):                  # 对话结束触发整理
        self._async_consolidate(llm_func)                        # 短期溢出→提炼中长期
```

**三层对照**
| 层 | 存储 | 内容 | 生命周期 |
|---|---|---|---|
| 短期 | Redis List（内存兜底） | 最近 N 轮原话 | TTL 2h |
| 中期 | Redis String | 对话摘要 | TTL 24h |
| 长期 | Chroma（向量） | 实体/知识，带遗忘衰减 | 永久 |

> `chat.py` 里 `mem.get_context(query)` 把三层拼成 `memory` 段塞进 Prompt；`mem.add` + `mem.trigger_background_jobs(call_llm)` 在回答后落库。

---

## 四、鉴权 `app/api/auth.py`

```python
JWT_ALGORITHM = "HS256"
TOKEN_EXPIRE_DAYS = 30

def _create_token(user_info: dict, expires_days=TOKEN_EXPIRE_DAYS) -> str:
    payload = {"sub": user_info.get("username",""),
               "tenant_id": user_info.get("tenant_id",""),
               "role": user_info.get("role","user"),
               "exp": datetime.now(timezone.utc) + timedelta(days=expires_days)}
    return jwt.encode(payload, cfg.JWT_SECRET, algorithm=JWT_ALGORITHM)   # HS256 签名

def get_user_from_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, cfg.JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(401, "Invalid or expired token")
    return {"username": payload.get("sub",""), "tenant_id": payload.get("tenant_id",""),
            "role": payload.get("role","user")}

def require_user(authorization: str = Header(...)) -> dict:     # FastAPI 依赖，被所有接口复用
    token = authorization.replace("Bearer ", "").strip()
    if not token:
        raise HTTPException(401, "Missing token")
    return get_user_from_token(token)
```

**要点**：`require_user` 是全局鉴权依赖，所有 `Depends(require_user)` 的接口都先跑它，解出 `tenant_id` 传给业务函数——**租户隔离的源头就在这里**。

---

## 五、一个完整请求的数据形态变化

**上传**
| 阶段 | 形态 |
|---|---|
| 入站 | `multipart/form-data` 字节流 |
| `get_safe_upload_path` | `uploads/<tenant>/xxx.pdf` 绝对路径 |
| `MultimodalPipeline.process` | `List[MultimodalChunk]` |
| `[c.text for c in chunks]` | `List[str]`（纯文本块） |
| `create_embedder().embed_documents` | `List[List[float]]`（向量） |
| `Chroma.from_texts().persist()` | 磁盘 `chroma_db/<tenant>/` |

**查询**
| 阶段 | 形态 |
|---|---|
| 入站 | `{"message": str, "history": [...], "stream": bool}` |
| `qr.rewrite` | `str`（改写后的问题） |
| `HybridRetriever.retrieve` | `List[Document]`（Top-10） |
| `_reranker.rerank` | `List[Document]`（Top-5） |
| `ct.format_context` | `str`（带 `[1]` 标记的上下文） |
| `call_llm` / 流式 `generate` | `str`（answer）+ `citations` |

---

## 六、自测：闭眼能写出下列函数签名 + 核心逻辑

1. `documents.py` → `upload_document()` 七步（校验→落盘→切块→向量化→persist）
2. `middleware.py` → `get_safe_upload_path` 三件套（tenant 清洗 + sanitize + is_safe_path）
3. `multimodal_pipeline.py` → `process` 三信号合并（text + OCR + caption）+ 500/50 切分
4. `embedder_factory.py` → `create_embedder` 默认 openai + `sorted(..., key=index)`
5. `chat.py` → `chat()` 流程（pipeline→rewrite→cache→retrieve→rerank→prompt→分流）
6. `hybrid_retriever.py` → `retrieve` 四步（dense/sparse/es→rrf→rerank）+ RRF 公式
7. `hybrid_retriever.py` → `Reranker.rerank` Cross-Encoder + 失败降级
8. `citation.py` → `format_context` 生成 `[i] 文件名 第N页`
9. `memory_manager.py` → 三层（short/mid/long）+ `get_context` 组装
10. `auth.py` → `require_user` 解 JWT 出 `tenant_id`

能默写这 10 个 = 真正吃透代码层。
