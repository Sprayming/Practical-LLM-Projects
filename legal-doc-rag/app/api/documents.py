import os, sys, json, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Header
from app.retrieval.embedder_factory import create_embedder
from app.processing.multimodal_pipeline import MultimodalPipeline
from langchain_community.vectorstores import Chroma
import app.core.config as cfg
from app.api.auth import get_user_from_token

router = APIRouter(prefix="/api/documents", tags=["documents"])

def _require_user(authorization: str = Header(...)) -> dict:
    token = authorization.replace("Bearer ", "").strip()
    if not token:
        raise HTTPException(401, "Missing token")
    return get_user_from_token(token)

@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    user: dict = Depends(_require_user),
):
    tenant_id = user["tenant_id"]
    upload_dir = os.path.join(cfg.UPLOAD_DIR, tenant_id)
    os.makedirs(upload_dir, exist_ok=True)

    file_path = os.path.join(upload_dir, file.filename)
    content = await file.read()
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
def list_documents(user: dict = Depends(_require_user)):
    tenant_id = user["tenant_id"]
    upload_dir = os.path.join(cfg.UPLOAD_DIR, tenant_id)
    if not os.path.exists(upload_dir):
        return {"documents": []}
    files = [f for f in os.listdir(upload_dir) if f.endswith(".pdf")]
    return {"documents": files}
