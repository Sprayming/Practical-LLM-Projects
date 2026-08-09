"""
独立重索引脚本（脱离 web 服务进程，避免后台线程被回收导致索引中断）。
用途：
  1. 遍历 chroma_db 下每个租户的 uploads，调用 MultimodalPipeline 处理；
  2. 有文字层 PDF 直接抽文字 → 分块 → 本地 BGE-M3 向量化；
  3. 无文字层扫描件通过 OCR（PaddleOCR）识别图片文字 → 分块 → 向量化；
  4. 识别结果为空 → 删除其历史垃圾 chunk（如旧版 [Image] 占位符），避免污染检索；
  5. 幂等：已索引的源会先清后写，可重复运行。
运行：python reindex_docs.py
注意：要在能 import paddleocr 的 Python 环境执行（如 .ocr_venv/Scripts/python）。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 离线加载本地 BGE-M3：必须在导入 app 模块之前设置好环境变量与 .env
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ.setdefault(
    "HF_MODEL_NAME", r"D:\git\legal-doc-rag\model_cache\bge-m3"
)
os.environ.setdefault("HF_CACHE_DIR", "./model_cache")
os.environ["HF_HUB_DISABLE_SYMLINKS"] = "1"
try:
    from dotenv import load_dotenv

    load_dotenv()  # 读取项目 .env（EMBEDDER_TYPE / HF_MODEL_NAME 等）
except Exception:
    pass

import chromadb
from app.core import config as cfg
from app.processing.multimodal_pipeline import MultimodalPipeline
from app.retrieval.embedder_factory import create_embedder
from app.retrieval.sparse_store import save_sparse

CHROMA_ROOT = cfg.CHROMA_PERSIST_DIR
UPLOAD_ROOT = cfg.UPLOAD_DIR

pipeline = MultimodalPipeline()


def extract_chunks(pdf_path: str):
    """调用多模态管线：文字层 + OCR + 图片 caption → 文本块列表。"""
    chunks = pipeline.process(pdf_path)
    return [c.text for c in chunks if c.text.strip()]


def reindex_tenant(tenant_id: str):
    upload_dir = os.path.join(UPLOAD_ROOT, tenant_id)
    persist_dir = os.path.join(CHROMA_ROOT, tenant_id)
    if not os.path.isdir(upload_dir):
        print(f"[tenant {tenant_id}] 无 uploads 目录，跳过")
        return

    client = chromadb.PersistentClient(path=persist_dir)
    try:
        col = client.get_collection("langchain")
    except Exception:
        col = client.create_collection("langchain")

    embedder = create_embedder()
    from app.retrieval.bge_m3_embedder import BGEM3Embedder
    is_bge = isinstance(embedder, BGEM3Embedder)

    pdfs = [f for f in os.listdir(upload_dir) if f.lower().endswith(".pdf")]
    if not pdfs:
        print(f"[tenant {tenant_id}] 无 PDF，跳过")
        return

    # 现有 chunk 的 source 分布
    existing = col.get(include=["metadatas"])["metadatas"] or []
    existing_sources = {m.get("source") for m in existing}

    for fname in pdfs:
        path = os.path.join(upload_dir, fname)
        print(f"  [处理] {fname}: 调用 MultimodalPipeline（含 OCR）...")
        chunks = extract_chunks(path)
        total_chars = sum(len(c) for c in chunks)

        if not chunks:
            # 无文字层且 OCR 也无效：清理历史垃圾 chunk
            if fname in existing_sources:
                try:
                    res = col.get(where={"source": fname})
                    del_ids = res.get("ids", [])
                    if del_ids:
                        col.delete(ids=del_ids)
                        print(f"  [清理] {fname}: 删除 {len(del_ids)} 个无文字层/无 OCR 垃圾 chunk")
                except Exception as e:
                    print(f"  [清理] {fname} 删除失败: {e}")
            else:
                print(f"  [跳过] {fname}: 抽取后无有效文本（无文字层且 OCR 未识别）")
            continue

        # 先清旧的，再写入（幂等）
        try:
            res = col.get(where={"source": fname})
            del_ids = res.get("ids", [])
            if del_ids:
                col.delete(ids=del_ids)
                print(f"  [清理] {fname}: 删除旧 chunk {len(del_ids)} 个（准备重建）")
        except Exception:
            pass

        print(f"  [索引] {fname}: 抽取 {len(chunks)} chunks（总字符 {total_chars}）")

        # BGE-M3 稀疏向量（检索时用于稀疏召回，失败不影响稠密）
        if is_bge:
            try:
                sp_items = [
                    {"key": t[:200], "sp": sp}
                    for t, sp in zip(chunks, embedder.encode_sparse(chunks))
                ]
                save_sparse(tenant_id, fname, sp_items)
            except Exception as e:
                print(f"    [warn] 稀疏向量生成失败（忽略）: {e}")

        embs = embedder.embed_documents(chunks)
        col.add(
            ids=[f"{fname}-{i}" for i in range(len(chunks))],
            documents=chunks,
            embeddings=embs,
            metadatas=[{"source": fname, "chunk": i} for i in range(len(chunks))],
        )
        print(f"    -> 已写入 {len(chunks)} chunks")

    print(f"[tenant {tenant_id}] 集合当前总数: {col.count()}")


if __name__ == "__main__":
    tenants = [
        d for d in os.listdir(CHROMA_ROOT)
        if os.path.isdir(os.path.join(CHROMA_ROOT, d))
    ] if os.path.isdir(CHROMA_ROOT) else []
    print("发现租户:", tenants)
    for t in tenants:
        reindex_tenant(t)
    print("全部重索引完成。")
