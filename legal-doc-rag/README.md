# Legal Document RAG

A legal document Q&A system built with Streamlit. Upload PDF contracts, regulations, or legal documents, then ask questions in natural language. The system retrieves relevant clauses and generates answers with source citations.

## Architecture

```
streamlit_app.py (entry point - ~220 lines)
  |
  +-- memory/memory_manager.py    3-layer memory (short/mid/long)
  |     +-- redis_client.py        Redis + TTL expiration + fallback
  |     +-- forgetting.py           Ebbinghaus forgetting curve
  |     +-- shadow_worker.py        Async background thread pool
  |
  +-- processing/multimodal_pipeline.py  PDF text + image extraction
  |     +-- pdf_extractor.py        PyMuPDF text + image extraction
  |     +-- ocr_engine.py           OCR (PaddleOCR / Tesseract)
  |
  +-- retrieval/
  |     +-- hybrid_retriever.py     BM25 + Dense + RRF + Cross-Encoder
  |     +-- query_rewriter.py       LLM query rewrite / expansion
  |     +-- citation.py             Source citation tracking
  |
  +-- evaluation/                   (offline - not in online flow)
  |     +-- evaluator.py            RAGAS 3-dimension scoring
  |     +-- runner.py               Batch evaluation with golden test set
  |
  +-- tenant/tenant_manager.py     Multi-tenant data isolation
  |
  +-- observability/tracker.py     Full-pipeline trace (duration, tokens)
  |
  +-- worker/shadow_worker.py      Shared async worker pool
```

## Import Graph

```
streamlit_app.py (main entry)
  +-- memory/memory_manager.py
  |     +-- memory/redis_client.py
  |     +-- memory/forgetting.py
  |     +-- worker/shadow_worker.py
  |
  +-- processing/multimodal_pipeline.py
  |     +-- processing/pdf_extractor.py
  |     +-- processing/ocr_engine.py
  |
  +-- retrieval/hybrid_retriever.py (contains Reranker class)
  |     +-- retrieval/citation.py
  |
  +-- retrieval/query_rewriter.py
  +-- observability/tracker.py
```

## Data Flow (Online)

```
User Input
  |
  v
MultimodalPipeline.process(PDF path)
  |  Extracts text from PDF, runs OCR on images,
  |  generates image captions, merges into chunks
  |  Output: MultimodalChunk[] with .text / .page_number / .images
  v
Chroma.from_texts(chunks) -> vector_store
HybridRetriever(dense_store, texts) -> retriever
  |
  v  (per user question)
QueryRewriter.rewrite(query)
  |  LLM rewrites/expands the question
  |  Output: rewritten search query
  v
HybridRetriever.invoke(search_query)
  |  BM25 + Dense + RRF fusion -> documents[]
  v
CitationTracker.add_sources(docs)
  |  Annotates each doc with source metadata
  |  format_context() -> annotated text
  |  format_citations() -> [source:N] list
  v
MemorySystem.get_context(query)
  |  1. long_term: Chroma similarity search + forgetting filter
  |  2. mid_term: Redis summary string
  |  3. short_term: last 4 rounds of raw conversation
  v
LLM (DeepSeek)
  |  Receives: system prompt + context + citations + memory + question
  |  Outputs: answer with [source:N] references
  v
MemorySystem.add(assistant, answer)
MemorySystem.extract_entities()
  |  ShadowWorker async: LLM extracts structured JSON entities
  |  -> stores into long-term ChromaDB
  v
TraceContext.print_summary() -> get_trace_store().save()
  |  Logs: query_rewrite_time, retrieve_time, generate_time, token_count
```

## Memory System (3-layer)

```
Short-term (last 6 rounds of raw text, ~600 tokens)
  Memory + Redis List (TTL 2h, auto-expire)
  Maintains current conversation coherence
  |
  v  (when short_term exceeds max = 6 rounds)
Mid-term (LLM-compressed summary, ~200 tokens)
  Memory + Redis String (TTL 24h)
  Keeps core intent + facts across rounds
  (incremental merge: old summary + new conversation -> LLM -> merged summary)
  |
  v  (async background via ShadowWorker)
Long-term (ChromaDB vector store, permanent)
  Ebbinghaus forgetting curve: score = 0.5 * recency + 0.3 * frequency + 0.2 * importance
  Async access_count bump on retrieval (re-activation)
  |
  v
Entity Profile (async extraction)
  LLM extracts structured JSON entities from each conversation round
  Stores as type=entity documents in long-term ChromaDB
```

## Token Budget

```
Layer                  Budget  Notes
-----                  ------  -----
System Prompt           ~100   Fixed
Short-term (6 rounds)  ~600   Auto-truncate oldest
Entity Profile         ~100   Structured JSON, always loaded
Long-term (retrieved)  ~500   Top-3, forgetting filtered
Retrieved docs         ~2000  Top-5, deduplicated
User input             <500   Front-end limited
Total                  ~3800  Room for response
```

## Quick Start

```bash
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple/
cp .env.example .env
# Edit .env: fill LLM_API_KEY
cd legal-doc-rag
streamlit run app/streamlit_app.py
```

## Tech Stack

| Component        | Choice                    | File |
|-----------------|---------------------------|------|
| Frontend UI     | Streamlit                 | streamlit_app.py |
| Embedding       | text2vec-base-chinese     | streamlit_app.py |
| Doc vectorstore | ChromaDB                  | streamlit_app.py |
| Memory store    | ChromaDB                  | memory/memory_manager.py |
| Cache layer     | Redis (optional, fallback)| memory/redis_client.py |
| LLM             | DeepSeek API              | streamlit_app.py |
| PDF parsing     | PyMuPDF + MultimodalPipeline| processing/ |
| Hybrid search   | BM25 + Dense + RRF        | retrieval/hybrid_retriever.py |
| Query rewrite   | LLM (DeepSeek)            | retrieval/query_rewriter.py |
| Citation        | Source tracking            | retrieval/citation.py |
| Async worker    | Thread pool (daemon)      | worker/shadow_worker.py |
| Trace           | In-memory store           | observability/tracker.py |

## Project Status

- [x] Basic RAG Q&A (document retrieval + source tracing)
- [x] 3-layer memory system (short/mid/long + entity profile)
- [x] Entity extraction (async LLM -> structured JSON)
- [x] Token stats and budget control
- [x] Hybrid retriever (BM25 + Dense + RRF)
- [x] Query rewriter (LLM query expansion)
- [x] Citation tracker (source annotation)
- [x] Multimodal pipeline (PDF text + image + OCR)
- [x] Async shadow worker (background memory consolidation)
- [x] Forgetting mechanism (Ebbinghaus curve)
- [x] Redis fault tolerance (in-memory fallback)
- [ ] Multi-tenant isolation
- [ ] RAGAS evaluation (offline runner)

## Changelog

### 2026-07-19: Wire up all dormant modules
- MultimodalPipeline: replaced PyPDF2 + splitter (text + images + OCR)
- HybridRetriever: replaced direct Chroma retriever (BM25 + Dense + RRF)
- QueryRewriter: LLM-based query rewriting before retrieval
- CitationTracker: source annotation for retrieved docs
- TraceContext: full pipeline timing + token tracking
- Removed PyPDF2 and RecursiveCharacterTextSplitter imports

### 2026-07-19: 5 production improvements (memory_manager.py)
1. clear_session: fix Redis stale data (clear before resetting session_id)
2. Async access_count bump: retrieval re-activates memories via ShadowWorker
3. Entity extraction: implemented (was pass)
4. Incremental summary merge: old + new -> LLM -> merged
5. Redis restore: _restore_from_redis() on startup

### 2026-07-18: Remove monkey patching
- Replaced patched_init / patched_retrieve / patched_async_consolidate with direct methods
- ForgettingMechanism and ShadowWorker now injected via __init__
- Fixed extract_entities stub, memory_llm callback
- Removed .orig file

### Earlier
- RAGAS evaluation framework (31 golden test cases, 4 metrics)
- Redis memory (short/mid/long + TTL auto-expire)
- Multimodal processing (PyMuPDF + OCR + vision caption)
- Hybrid search (BM25 + Dense + RRF + Cross-Encoder)
- Query rewriter (LLM expansion + rule-based fallback)
- Citation tracker (source annotation)
- Observable tracker (full-pipeline trace)
- Async shadow worker (priority queue + retry)
- Forgetting mechanism (Ebbinghaus curve)
- Multi-tenant isolation (ChromaDB collection prefix)
- Memory system (monkey patched version, replaced 2026-07-18)

## Interview Q&A

### Q1: Why BM25 + Dense + RRF instead of pure semantic search?
BM25 excels at exact keyword matching (clause numbers, legal terms). Dense vectors capture synonyms and paraphrases. RRF fuses both rankings without tuning. Pure semantic search misses exact matches, pure BM25 misses semantic matches.

### Q2: How does Cross-Encoder differ from Bi-Encoder?
Bi-Encoder encodes query and doc separately, fast but less accurate. Cross-Encoder processes query+doc as a pair, more accurate but slower. Production: Bi-Encoder for first-stage recall (top-100), Cross-Encoder for re-ranking (top-30).

### Q3: Why chunk_size=500, overlap=50?
Too small (128) loses semantic completeness. Too large (1024+) mixes multiple topics. 500 is empirical. Overlap 50 (10%) prevents key sentences from being split at boundaries.

### Q4: How does RAGAS scoring work?
1. Faithfulness: split answer into claims, check each against retrieved context
2. AnswerRelevancy: reverse-generate questions from answer, measure similarity to original question
3. ContextPrecision: proportion of relevant chunks among retrieved results
4. ContextRecall: check if ground-truth claims appear in retrieved results

### Q5: How does multimodal PDF parsing work?
PyMuPDF extracts images from PDF pages. Vision LLM (via API) generates captions for each image. OCR extracts text from images. Caption + OCR text merged into the page's text chunk. Result: search 'chart' finds chart images.

### Q6: How is the memory system designed?
3-layer: short-term (last N raw rounds, Redis List TTL 2h), mid-term (LLM summary, Redis String TTL 24h), long-term (ChromaDB vector store, permanent). Background Worker async consolidates short->mid->long. Forgetting mechanism based on Ebbinghaus curve auto-filters low-score memories.

### Q7: What was the biggest technical challenge?
Golden Test Set design. Different people write ground truth inconsistently, causing RAGAS score oscillation. Unified template with question / ground_truth / source_doc / difficulty. Stabilized evaluation before doing any optimization.

### Q8: Why not use LangChain/LlamaIndex end-to-end?
They provide base components. We customized at 3 layers: retrieval strategy (BM25+Dense+RRF+Cross-Encoder), memory system (Redis+forgetting+async Worker), evaluation system (RAGAS+31 test cases). Framework for infrastructure, custom code for business logic.

## How to Learn This Codebase

1. Start with streamlit_app.py - understand the full flow (2 hours)
2. Study memory/memory_manager.py - memory system (3 hours)
3. Study retrieval/hybrid_retriever.py - hybrid search (2 hours)
4. Prepare for follow-up questions (2 hours)
5. Practice explaining without looking at code (1 hour)

