"""
reindex_docs.py —— 独立文档重索引脚本

【作用与功能】
本脚本脱离 web 服务进程，对 chroma_db 下各租户的 uploads 全量重做向量索引，避免后台线程
被回收导致索引中断。支持有文字层 PDF 直抽、扫描件经 OCR(PaddleOCR)识别、识别为空时
清理历史垃圾 chunk，并以"先清后写"保证幂等，可重复安全运行。

【主要组成】
- `extract_chunks`:调用多模态管线抽取 PDF 文本块(含 OCR/图片 caption)。
- `reindex_tenant`:对单个租户执行全量重索引(抽取→向量化→分批写入/清理垃圾)。
- `__main__`:扫描所有租户目录并逐个调用 `reindex_tenant`。

【适用场景】
- 向量库损坏或模型/分块策略变更后，离线重建全量索引。
- 单独排查或重建某个租户索引时直接调用 `reindex_tenant`。

【依赖关系】
- 上游调用方:命令行 `python reindex_docs.py`。
- 下游依赖:app.core.config、app.processing.multimodal_pipeline、app.retrieval.embedder_factory、
  app.retrieval.sparse_store、chromadb、PaddleOCR、本地 BGE-M3 模型。
"""
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 离线加载本地 BGE-M3:必须在导入 app 模块之前设置好环境变量与 .env
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ.setdefault(
    "HF_MODEL_NAME", r"D:\git\legal-doc-rag\model_cache\bge-m3"
)
os.environ.setdefault("HF_CACHE_DIR", "./model_cache")
os.environ["HF_HUB_DISABLE_SYMLINKS"] = "1"
try:
    from dotenv import load_dotenv

    load_dotenv()  # 读取项目 .env(EMBEDDER_TYPE / HF_MODEL_NAME 等)
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
    """调用多模态管线抽取 PDF 文本块。

    依次尝试从 PDF 中提取文字层、OCR 扫描件文字以及图片 caption，
    将管线产出的有效 chunk 收敛为纯文本字符串列表。

    参数:
        pdf_path (str): 待处理的 PDF 文件绝对/相对路径
    返回:
        list[str]: 经去空白过滤后的有效文本块列表(可能为空)
    适用场景:
        - 在重索引流程中作为「抽取」环节，为后续向量化提供文本来源
    """
    chunks = pipeline.process(pdf_path)
    return [c.text for c in chunks if c.text.strip()]


def reindex_tenant(tenant_id: str):
    """对单个租户执行全量重索引。

    遍历该租户 uploads 目录下的所有 PDF，逐一抽取文本并向量化写入
    对应 Chroma 集合；对无有效文本的 PDF 清理历史垃圾 chunk；
    整个过程幂等(先清旧 chunk 再写入)，单文件失败不影响其他文件。

    参数:
        tenant_id (str): 租户标识，对应 chroma_db 与 uploads 下的子目录名
    返回:
        无(直接打印处理进度与结果统计)
    适用场景:
        - 由 `__main__` 入口遍历所有租户逐个调用
        - 单独排查/重建某个租户索引时可直接调用
    """
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
        try:
            path = os.path.join(upload_dir, fname)
            print(f"  [处理] {fname}: 调用 MultimodalPipeline(含 OCR)...", flush=True)
            chunks = extract_chunks(path)
            total_chars = sum(len(c) for c in chunks)

            if not chunks:
                # 无文字层且 OCR 也无效:清理历史垃圾 chunk
                if fname in existing_sources:
                    try:
                        res = col.get(where={"source": fname})
                        del_ids = res.get("ids", [])
                        if del_ids:
                            col.delete(ids=del_ids)
                            print(f"  [清理] {fname}: 删除 {len(del_ids)} 个无文字层/无 OCR 垃圾 chunk", flush=True)
                    except Exception as e:
                        print(f"  [清理] {fname} 删除失败: {e}", flush=True)
                else:
                    print(f"  [跳过] {fname}: 抽取后无有效文本(无文字层且 OCR 未识别)", flush=True)
                continue

            # 先清旧的，再写入(幂等)
            try:
                res = col.get(where={"source": fname})
                del_ids = res.get("ids", [])
                if del_ids:
                    col.delete(ids=del_ids)
                    print(f"  [清理] {fname}: 删除旧 chunk {len(del_ids)} 个(准备重建)", flush=True)
            except Exception:
                pass

            print(f"  [索引] {fname}: 抽取 {len(chunks)} chunks(总字符 {total_chars})", flush=True)

            # 分批向量化 + 增量写入:降低峰值内存，单批失败不影响整体可重跑
            BATCH = 64
            all_sp_items = []
            written = 0
            for s in range(0, len(chunks), BATCH):
                batch = chunks[s:s + BATCH]
                if is_bge:
                    try:
                        sp = embedder.encode_sparse(batch)
                        all_sp_items.extend(
                            {"key": t[:200], "sp": w} for t, w in zip(batch, sp)
                        )
                    except Exception as e:
                        print(f"    [warn] 稀疏向量生成失败(忽略): {e}", flush=True)
                embs = embedder.embed_documents(batch)
                col.add(
                    ids=[f"{fname}-{s + i}" for i in range(len(batch))],
                    documents=batch,
                    embeddings=embs,
                    metadatas=[{"source": fname, "chunk": s + i} for i in range(len(batch))],
                )
                written += len(batch)
                print(f"    -> 已写入 {written}/{len(chunks)} chunks", flush=True)

            # 稀疏向量落盘(整文件覆盖写，需全部累积后一次保存)
            if is_bge and all_sp_items:
                try:
                    save_sparse(tenant_id, fname, all_sp_items)
                except Exception as e:
                    print(f"    [warn] 稀疏向量落盘失败(忽略): {e}", flush=True)

            print(f"  [完成] {fname}: 共写入 {len(chunks)} chunks", flush=True)
        except Exception as e:
            print(f"  [ERROR] {fname} 处理失败: {e}", flush=True)
            traceback.print_exc()
            continue

    print(f"[tenant {tenant_id}] 集合当前总数: {col.count()}")


if __name__ == "__main__":
    # 扫描 chroma_db 根目录下所有子目录作为租户列表，逐个重索引
    tenants = [
        d for d in os.listdir(CHROMA_ROOT)
        if os.path.isdir(os.path.join(CHROMA_ROOT, d))
    ] if os.path.isdir(CHROMA_ROOT) else []
    print("发现租户:", tenants)
    for t in tenants:
        reindex_tenant(t)
    print("全部重索引完成。")
