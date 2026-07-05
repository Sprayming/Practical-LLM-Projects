# Dental RAG System — Bug Fixes & Debugging Log

## 问题概览

修复了 7 类共 15+ 个 bug，覆盖 import 错误、语法错误、API 不兼容、编码问题等。  
以下按修复顺序排列。

---

## 1. 编码：.env 文件 BOM（Byte Order Mark）

**症状**：`settings.llm_api_key` 始终为空字符串，DeepSeek API 返回 `Authentication Fails (governor)`

**根因**：`.env` 文件用 `Out-File -Encoding UTF8` 创建，PowerShell 自动添加了 UTF-8 BOM（`\xEF\xBB\xBF`）。  
pydantic-settings 解析时将 BOM 视为键名的一部分，导致 `LLM_API_KEY` 未被识别。

**修复**：用二进制模式读取 `.env`，移除前 3 字节 BOM。

**教训**：在 Windows 上创建 .env 文件时优先用 `Set-Content` 或指定 `-Encoding ASCII`。

---

## 2. 路由路径：chat.py 路径写死

**文件**：`app/api/chat.py`

**症状**：前端请求 `POST /api/chat/` 返回 404

**根因**：路由定义为 `@router.post("/chat", ...)`，实际路径是 `/api/chat/chat`

**修复**：改为 `@router.post("/", ...)`

---

## 3. ChromaDB API 参数不兼容

**文件**：`app/retrieval/vector_store.py`

### 3a. query() 参数名

**症状**：`Collection.query()` 报 `TypeError: unexpected keyword argument 'top_k'`

**根因**：ChromaDB v0.5+ 的 query 方法使用 `n_results` 而非 `top_k`

**修复**：`top_k=top_k` → `n_results=top_k`

### 3b. include 参数

**症状**：`ValueError: Expected include item to be one of documents, embeddings, metadatas, distances, uris, data, got ids`

**根因**：`ids` 不是 ChromaDB query() 和 get() 方法的有效 include 选项

**修复**：`include=["documents", "metadatas", "ids", "distances"]` → `include=["documents", "metadatas", "distances"]`

---

## 4. Model 类名与 import 不匹配

多处文件引用了不存在的类名，所有 import 统一修正如下：

| 文件 | 旧写法 | 新写法 |
|------|--------|--------|
| `main.py` | `ErrorResponse` | `ErrorResponseModel` |
| `main.py` | `HealthResponse` | `HealthResponseModel` |
| `main.py` | `settings.api_key` | `settings.llm_api_key` |
| `chat.py` | `ChatRequest` | `ChatRequestModel` |
| `chat.py` | `ChatResponse` | `ChatResponseModel` |
| `retriever.py` | `CitationSource` | `CitationSourceModel` |
| `vector_store.py` | `DocumentMeta` | `DocumentMetaModel` |
| `llm.py` | `CitationSource` | `CitationSourceModel` |

---

## 5. Config 字段名不匹配

多处使用了不存在的配置字段：

| 文件 | 旧写法 | 新写法 |
|------|--------|--------|
| `llm.py` | `settings.DEEPSEEK_API_KEY` | `settings.llm_api_key` |
| `llm.py` | `settings.DEEPSEEK_API_URL` | `settings.llm_base_url` |
| `llm.py` | `settings.DEEPSEEK_MODEL` | `settings.llm_model` |
| `embedder.py` | `settings.EMBEDDING_DIM` | `settings.embedding_dimensions` |
| `vector_store.py` | `settings.CHROMA_PERSIST_DIR` | `settings.chroma_persist_dir` |
| `retriever.py` | `settings.RETRIEVER_TOP_K` | `settings.retrieval_top_k` |
| `retriever.py` | `settings.RETRIEVER_MIN_SCORE` | `settings.retrieval_min_score` |
| `main.py` | `settings.api_key` | `settings.llm_api_key` |

---

## 6. 缺失常量定义

**文件**：`app/config.py`

**症状**：`vector_store.py` 导入 `CHROMA_COLLECTION_NAME` 报 `ImportError`

**修复**：在 config.py 末尾添加 `CHROMA_COLLECTION_NAME: str = "dental_rag"`

---

## 7. loader.py：函数定义先于引用

**文件**：`app/ingestion/loader.py`

**症状**：`NameError: name '_load_pdf' is not defined`

**根因**：`LOADERS` 字典在模块顶部定义，引用尚未定义的 `_load_*` 函数。  
Python 执行模块时按顺序解析，此时函数尚未创建。

**修复**：将 `LOADERS` 字典移到文件末尾所有函数定义之后。

---

## 8. chunker.py：DocumentChunker 与 LoadedDocument 不匹配

**文件**：`app/ingestion/chunker.py`

### 8a. _validate_document 检查了错误的属性

**症状**：`"Document must have content attribute"`

**根因**：`DocumentChunker._validate_document` 检查 `document.content` 和 `document.metadata`，  
但 `loader.py` 的 `LoadedDocument` 类的属性是 `full_text`、`pages`、`file_path`、`filename`、`metadata`

**修复**：  
- `hasattr(document, 'content')` → `hasattr(document, 'full_text')`  
- `hasattr(document, 'metadata')` → `hasattr(document, 'pages')`

### 8b. chunk() 使用了错误的字段

**症状**：`AttributeError: 'LoadedDocument' object has no attribute 'content'`

**修复**：`self._preprocess_content(document.content)` → `self._preprocess_content(document.full_text)`

### 8c. _process_paragraph 缺少 self

**症状**：无法调用，参数数量不匹配

**修复**：函数定义添加 `self` 参数，`chunk()` 调用时传入正确参数

---

## 9. retriever.py：CitationSourceModel 构造参数错误

**文件**：`app/retrieval/retriever.py`

**症状**：`ValidationError: content Field required`

**根因**：构造 `CitationSourceModel` 时使用了不存在的字段名  
`page=` 应为 `page_number=`，`document=` 应为 `content=`，  
且 `chunk_index=` 和 `score=` 在多次修复中被意外覆盖丢失

**修复**：重新构造参数列表

---

## 10. 方法调用名错误：embedder

**文件**：`app/retrieval/retriever.py`

**症状**：`AttributeError: 'Embedder' object has no attribute 'embed'`

**根因**：调用了 `self._embedder.embed(query)` 但方法名为 `embed_query`

**修复**：`embed()` → `embed_query()`

---

## 11. LLM 消息格式嵌套错误

**文件**：`app/generation/llm.py`

**症状**：DeepSeek API 返回 `"Failed to deserialize the JSON body into the target type: messages[0]: missing field 'type'"`

**根因**：`build_qa_prompt()` 已经返回完整的 messages 列表，但 `generate()` 方法将其再包裹一层：  
```python
# 错误
messages=[{"role": "user", "content": prompt}]

# 实际发送的 JSON 结构
{"messages": [{"role": "user", "content": [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "..."}
]}]}
```

DeepSeek API 认为 `content` 是 content parts 数组（OpenAI 新格式），要求每部分有 `type` 字段。

**修复**：`messages=[{"role": "user", "content": prompt}]` → `messages=prompt`

---

## 12. embedder.py 语法错误

**文件**：`app/retrieval/embedder.py`

**症状**：Python 解析失败

**根因**：`def __init__(self, dim锛歩nt | None = None)`  
参数列表的冒号使用了中文全角 `锛?`（用户已自行修复）

---

## 13. 排序：问题排查顺序

```
1. import 错误              → 修正类名/字段名
2. 语法错误                 → 用户自行修复
3. 配置缺失                 → 添加 CHROMA_COLLECTION_NAME
4. 代码执行顺序问题          → 移动 LOADERS 定义
5. 类接口不匹配              → DocumentChunker 适配 LoadedDocument
6. ChromaDB API 不兼容       → n_results / include 修正
7. 路由路径错误              → /chat → /
8. LLM 消息格式错误           → messages=prompt
9. .env BOM                 → 移除 UTF-8 BOM
```

`@` 符号在这里是共用的，一个 `@` 管全场。避免使用 `@` 作为评论标记。

