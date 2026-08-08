import os, sys, json, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from loguru import logger
from app.retrieval.embedder_factory import create_embedder
from app.processing.multimodal_pipeline import MultimodalPipeline
from langchain_community.vectorstores import Chroma
import app.core.config as cfg
from app.api.auth import get_user_from_token, require_user
from app.security.middleware import get_safe_upload_path, sanitize_filename

router = APIRouter(prefix="/api/documents", tags=["documents"])

# Allowed file extensions
ALLOWED_EXTENSIONS = {".pdf"}

# Max file size: 100MB
MAX_FILE_SIZE = 100 * 1024 * 1024

@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    user: dict = Depends(require_user),
):
    tenant_id = user["tenant_id"]

    # Validate file extension
    if not file.filename:
        raise HTTPException(400, "No filename provided")
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"File type not allowed. Allowed: {ALLOWED_EXTENSIONS}")

    # Read content and check size
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(413, f"File too large. Maximum size: {MAX_FILE_SIZE // (1024*1024)}MB")

    # Get safe file path (prevents path traversal)
    file_path = get_safe_upload_path(cfg.UPLOAD_DIR, tenant_id, file.filename)

    with open(file_path, "wb") as f:
        f.write(content)

    try:
        pipeline = MultimodalPipeline()
        chunks = pipeline.process(file_path)
    except Exception as e:
        raise HTTPException(500, f"PDF processing failed: {e}")

    if not chunks:
        raise HTTPException(400, "No text extracted from PDF")

    texts = [c.text for c in chunks]
    embedder = create_embedder()

    # 生成并持久化 BGE-M3 稀疏向量（失败不影响稠密入库，检索时自动降级）
    try:
        from app.retrieval.bge_m3_embedder import BGEM3Embedder
        from app.retrieval.sparse_store import save_sparse

        if isinstance(embedder, BGEM3Embedder):
            sp_items = [
                {"key": t[:200], "sp": sp}
                for t, sp in zip(texts, embedder.encode_sparse(texts))
            ]
            save_sparse(tenant_id, file.filename, sp_items)
            logger.info("BGE-M3 稀疏向量已持久化: {} chunks", len(sp_items))
    except Exception as e:  # noqa: BLE001
        logger.warning("稀疏向量生成失败（不影响稠密入库）: {}", e)

    persist_dir = os.path.join(cfg.CHROMA_PERSIST_DIR, tenant_id)
    vector_store = Chroma.from_texts(
        texts=texts,
        embedding=embedder,
        metadatas=[{"source": file.filename, "chunk": i} for i in range(len(texts))],
        persist_directory=persist_dir,
    )
    vector_store.persist()

    return {
        "success": True,
        "filename": file.filename,
        "chunks": len(texts),
        "tenant_id": tenant_id,
    }

@router.get("")
def list_documents(user: dict = Depends(require_user)):
    tenant_id = user["tenant_id"]
    upload_dir = os.path.join(cfg.UPLOAD_DIR, tenant_id)
    if not os.path.exists(upload_dir):
        return {"documents": []}
    files = [f for f in os.listdir(upload_dir) if f.endswith(".pdf")]
    return {"documents": files}

@router.get("/preview/{filename}")
async def preview_document(filename: str, user: dict = Depends(require_user)):
    """预览PDF文档"""
    tenant_id = user["tenant_id"]

    # Sanitize filename
    safe_filename = sanitize_filename(filename)
    upload_dir = os.path.join(cfg.UPLOAD_DIR, tenant_id)
    file_path = os.path.join(upload_dir, safe_filename)

    # Verify path is safe
    from app.security.middleware import is_safe_path
    if not is_safe_path(upload_dir, file_path):
        raise HTTPException(400, "Invalid filename")

    # Check if file exists
    if not os.path.exists(file_path):
        raise HTTPException(404, "Document not found")

    # Return file for preview
    from fastapi.responses import FileResponse
    return FileResponse(
        path=file_path,
        media_type="application/pdf",
        filename=safe_filename,
    )

@router.delete("/{filename}")
def delete_document(filename: str, user: dict = Depends(require_user)):
    """删除文档（仅管理员）"""
    tenant_id = user["tenant_id"]
    role = user.get("role", "user")

    if role != "super_admin":
        raise HTTPException(403, "仅管理员可以删除文档")

    # Sanitize filename to prevent path traversal
    safe_filename = sanitize_filename(filename)
    upload_dir = os.path.join(cfg.UPLOAD_DIR, tenant_id)
    file_path = os.path.join(upload_dir, safe_filename)

    # Verify path is safe
    from app.security.middleware import is_safe_path
    if not is_safe_path(upload_dir, file_path):
        raise HTTPException(400, "Invalid filename")

    deleted = False
    if os.path.exists(file_path):
        os.remove(file_path)
        deleted = True

    # 从 ChromaDB 删除对应的向量数据
    persist_dir = os.path.join(cfg.CHROMA_PERSIST_DIR, tenant_id)
    if os.path.exists(persist_dir):
        try:
            vector_store = Chroma(
                embedding_function=create_embedder(),
                persist_directory=persist_dir,
            )
            results = vector_store.get(where={"source": filename})
            ids = results.get("ids", [])
            if ids:
                vector_store.delete(ids=ids)
                vector_store.persist()
        except Exception:
            pass

    # 同步删除 BGE-M3 稀疏向量文件
    try:
        from app.retrieval.sparse_store import delete_sparse

        delete_sparse(tenant_id, filename)
    except Exception:
        pass

    if not deleted:
        raise HTTPException(404, "Document not found")

    return {"success": True, "message": f"{filename} 已删除"}

