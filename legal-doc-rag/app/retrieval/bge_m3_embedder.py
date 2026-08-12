"""
bge_m3_embedder.py —— BGE-M3 嵌入器：同时提供稠密向量与 SPLADE 稀疏权重

【作用与功能】
该模块在 legal-doc-rag 检索链路中提供向量化能力，封装 BGE-M3 模型，
同时输出稠密（1024 维）与稀疏（SPLADE 词汇权重）两种向量，供 Chroma 入库
与 RRF 融合召回使用。其稀疏向量由本模块确定性自计算，规避 FlagEmbedding
`_sparse_embedding` 在 CPU 下偶发丢值的缺陷，且模型以进程内单例加载以节省显存。

【主要组成】
- `get_bge_m3_model`：懒加载并返回 BGEM3FlagModel 单例（失败降级为 None）
- `encode_sparse_direct`：直接基于编码器 + sparse_linear 确定性计算 SPLADE 稀疏字典
- `BGEM3Embedder`：langchain 兼容的嵌入器，提供稠密接口与稀疏接口

【适用场景】
- 场景1：文档入库/查询时生成稠密向量供 Chroma 使用
- 场景2：混合检索中生成稀疏权重，与 BM25/稠密做 RRF 融合以提升法律术语召回

【依赖关系】
- 上游调用方：HybridRetriever（稀疏召回）、入库流程（稠密入库）
- 下游依赖：FlagEmbedding.BGEM3FlagModel、torch、langchain_core.embeddings.Embeddings
"""
import os
import threading
from typing import Dict, List, Optional

import torch
from langchain_core.embeddings import Embeddings

_MODEL = None
_MODEL_LOCK = threading.Lock()
_ENCODE_LOCK = threading.Lock()


def _unused_token_ids(tokenizer) -> set:
    """收集 BGE-M3 tokenizer 的特殊 token id（这些 token 不应进入稀疏词典）。"""
    unused = set()
    for key in ("cls_token", "eos_token", "pad_token", "unk_token"):
        if key in tokenizer.special_tokens_map:
            try:
                unused.add(
                    tokenizer.convert_tokens_to_ids(tokenizer.special_tokens_map[key])
                )
            except Exception:  # noqa: BLE001
                pass
    return unused


def _get_device(module: torch.nn.Module) -> torch.device:
    """推断给定模块所在的设备（CPU/GPU）。

    通过取模块第一个参数的 device 判断其所在设备；若模块无参数或出错，
    则回退到 CPU。用于在稀疏编码前确定张量应放置的设备。

    参数:
        module (torch.nn.Module): 待推断设备的模型模块
    返回:
        torch.device: 模型所在设备（如 cpu / cuda:0）
    """
    try:
        return next(module.parameters()).device
    except Exception:  # noqa: BLE001
        return torch.device("cpu")


def get_bge_m3_model():
    """懒加载并返回 BGEM3FlagModel 单例；加载失败返回 None（稀疏能力降级关闭）。"""
    global _MODEL
    if _MODEL is not None:
        return _MODEL if _MODEL else None
    with _MODEL_LOCK:  # 双重检查锁定：仅首个线程进入加载，其余直接复用
        if _MODEL is not None:
            return _MODEL if _MODEL else None
        try:
            from FlagEmbedding import BGEM3FlagModel

            model_name = os.getenv("HF_MODEL_NAME", "BAAI/bge-m3")
            # FP16：权重减半（约 2GB），检索质量无损，显著降低内存峰值，
            # 也让沙箱/低内存机器能跑起重索引与服务。
            inst = BGEM3FlagModel(model_name, use_fp16=True)
            # warm-up：触发稠密前向（Transformer 编译/首次推理开销），
            # 稀疏路径复用同一 Transformer，无需重复 warm-up。
            try:
                inst.encode(
                    ["warmup"],
                    return_dense=True,
                    return_sparse=False,
                    return_colbert_vecs=False,
                )
            except Exception:  # noqa: BLE001
                pass
            _MODEL = inst
        except Exception as e:  # noqa: BLE001
            try:
                import loguru

                loguru.logger.warning("BGEM3FlagModel 加载失败，稀疏向量不可用: {}", e)
            except Exception:  # noqa: BLE001
                pass
            _MODEL = False  # 标记失败，避免反复尝试
    return _MODEL if _MODEL else None


def encode_sparse_direct(
    model, texts: List[str], batch_size: int = 16
) -> List[Dict[str, float]]:
    """确定性地计算 BGE-M3 SPLADE 稀疏权重字典列表。

    绕过 FlagEmbedding 的 `_sparse_embedding`（内部 scatter_reduce(reduce="amax") 在
    CPU 下偶发整条稀疏向量丢失）。这里直接使用模型自身的 XLM-RoBERTa 编码器 +
    逐位置标量门控 `sparse_linear`，按 token id 取最大门控权重（=amax）聚合成词表
    维度稀疏向量，再组装为 {token_id: weight}。结果 100% 可复现，不依赖库的稀疏实现。

    参数:
        model: BGEM3FlagModel 实例
        texts: 待编码文本列表
    返回:
        与 texts 等长的列表，每项为 {str(token_id): float(weight)}（可能为空字典）
    """
    if not texts:
        return []

    inner = model.model  # Inference BGEM3Model
    transformer = inner.model  # XLM-RoBERTa 编码器
    sparse_linear = inner.sparse_linear
    tokenizer = model.tokenizer

    device = _get_device(sparse_linear)
    was_training = transformer.training
    transformer.eval()
    inner.eval()

    unused = _unused_token_ids(tokenizer)
    results: List[Dict[str, float]] = []

    try:
        for start in range(0, len(texts), batch_size):
            batch = texts[start : start + batch_size]
            enc = tokenizer(
                batch,
                padding=True,
                truncation=True,
                max_length=512,
                return_tensors="pt",
            )
            input_ids = enc["input_ids"].to(device)
            attention_mask = enc["attention_mask"].to(device)

            with torch.no_grad():
                out = transformer(input_ids=input_ids, attention_mask=attention_mask)
                hidden = out.last_hidden_state  # (B, S, H)
                # BGE-M3 的稀疏头是逐 token 位置的标量门控：Linear(H -> 1)。
                # 真正 SPLADE 词表向量 = 按 input_ids 把每个位置的门控权重聚合到词表维度
                # （FlagEmbedding 用 scatter_reduce(reduce="amax")，CPU 下曾偶发丢值）。
                # 这里用确定性方式：对每个 token id 取其在序列中的最大门控权重（=amax），
                # 数学上等价且 100% 可复现，不依赖库的 scatter_reduce。
                gate = torch.relu(sparse_linear(hidden)).squeeze(-1)  # (B, S)

            gate_np = gate.cpu().numpy()
            ids_np = input_ids.cpu().numpy()
            mask_np = attention_mask.cpu().numpy()

            for b in range(gate_np.shape[0]):
                d: Dict[str, float] = {}
                seq_ids = ids_np[b]
                seq_gate = gate_np[b]
                seq_mask = mask_np[b]
                for p in range(seq_ids.shape[0]):
                    if seq_mask[p] == 0:  # 跳过 pad
                        continue
                    idx = int(seq_ids[p])
                    if idx in unused:  # 跳过特殊 token
                        continue
                    w = float(seq_gate[p])
                    if w > 0:
                        s = str(idx)
                        if w > d.get(s, 0.0):
                            d[s] = w
                results.append(d)
    finally:
        if was_training:
            transformer.train()

    return results


# 向后兼容别名
encode_sparse_safe = encode_sparse_direct


class BGEM3Embedder(Embeddings):
    """langchain 兼容的 BGE-M3 嵌入器（稠密 + 稀疏）。"""

    def __init__(self):
        """初始化 langchain 兼容的 BGE-M3 嵌入器。

        构造时懒加载全局 BGE-M3 模型单例（进程内仅一份权重）。
        模型加载失败时 self._model 为 None：稠密接口抛错、稀疏接口降级返回空。
        """
        self._model = get_bge_m3_model()

    # ---------- langchain 稠密接口 ----------
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """批量生成稠密向量（langchain Embeddings 接口）。

        调用底层 BGEM3FlagModel 的稠密编码并取 dense_vecs 转 list 返回，
        供 Chroma 入库与查询。模型未加载时抛出 RuntimeError。

        参数:
            texts (List[str]): 待编码文本列表
        返回:
            List[List[float]]: 与输入等长的 1024 维稠密向量列表
        异常:
            RuntimeError: BGEM3FlagModel 未成功加载时抛出
        """
        if self._model is None:
            raise RuntimeError("BGEM3FlagModel 未加载，无法生成稠密向量")
        out = self._model.encode(
            texts,
            return_dense=True,
            return_sparse=False,
            return_colbert_vecs=False,
            batch_size=16,
        )
        return out["dense_vecs"].tolist()

    def embed_query(self, text: str) -> List[float]:
        """生成单个查询的稠密向量（langchain Embeddings 接口）。

        复用 embed_documents 对单条文本编码并取首个结果，确保与文档同处
        一个向量空间，便于相似度检索。

        参数:
            text (str): 查询文本
        返回:
            List[float]: 1024 维稠密向量
        """
        return self.embed_documents([text])[0]

    # ---------- 稀疏接口（BGE-M3 SPLADE，自计算，确定性） ----------
    def encode_sparse(self, texts: List[str]) -> List[Dict[str, float]]:
        """返回每个文本的稀疏权重字典 {token_id: weight}。"""
        if self._model is None:
            return [{} for _ in texts]
        return encode_sparse_direct(self._model, texts)

    def encode_query_sparse(self, text: str) -> Dict[str, float]:
        """生成单个查询的 BGE-M3 SPLADE 稀疏权重字典。

        便于单查询场景复用 encode_sparse 的确定性自计算路径，
        返回 {token_id: weight}；模型不可用时为空字典。

        参数:
            text (str): 查询文本
        返回:
            Dict[str, float]: 稀疏权重字典
        """
        res = self.encode_sparse([text])
        return res[0]
