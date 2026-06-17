# ============================================================
# 嵌入服务 — 把中文文本转成向量（数字数组）
#
# 用 jieba 分词 + 字符 n-gram 哈希生成向量
# 特点：完全本地运行，不需要任何 API Key
# 不是最精确的嵌入方法（比不上 BERT），但零依赖、秒级可用
#
# 原理：
#   · 先用 jieba 把中文句子切成词（"报销流程" → ["报销","流程"]）
#   · 每个词通过 MD5 哈希映射到向量的一个位置
#   · 再加字符 bigram 做细粒度补充
#   · 最后归一化让向量长度为 1（方便算余弦相似度）
# ============================================================

from __future__ import annotations

import hashlib
from typing import Optional

import numpy as np                     # 科学计算库，用于向量运算
from loguru import logger

from app.config import settings


class Embedder:
    """本地嵌入器。
    
    用 jieba 做中文分词，通过哈希把词映射到向量空间。
    输出：768 维的归一化浮点数向量。
    """

    def __init__(self, dim: int | None = None) -> None:
        # 向量维度，默认 768（越大信息量越大，但计算越慢）
        self.dim = dim or settings.embedding_dimensions
        
        # jieba 是中文分词库，import 时会加载词典
        # 首次运行会花 1 秒左右建缓存，之后就快了
        import jieba
        self._jieba = jieba
        
        logger.info("Embedder ready: jieba + ngram, dim={}", self.dim)

    def _vec(self, text: str) -> list[float]:
        """把一段文本转成 768 维的向量。"""
        vec = np.zeros(self.dim, dtype=np.float32)  # 初始化为全 0 向量

        # ── 第1层：词级别特征（高权重 1.0） ──
        # jieba.cut 把句子切成词，如"报销流程" → ["报销","流程"]
        for w in self._jieba.cut(text):
            w = w.strip()
            if not w:
                continue
            # MD5 把词 → 哈希值 → 取前4字节 → 模 dimension → 得到向量位置
            # 同一个词永远映射到同一个位置
            h = int.from_bytes(hashlib.md5(w.encode()).digest()[:4], "little") % self.dim
            vec[h] += 1.0  # 在这个位置上"加 1"

        # ── 第2层：字符 bigram 特征（低权重 0.3） ──
        # "报销" → "报"+"销" → 2-gram "报销"
        # 这种细粒度特征可以补充分词没覆盖到的信息
        for i in range(len(text) - 1):
            h = int.from_bytes(
                hashlib.md5(text[i:i+2].encode()).digest()[:4], "little"
            ) % self.dim
            vec[h] += 0.3

        # ── 归一化 ──
        # 让向量的长度 = 1，这样算余弦相似度时直接用点积就行
        norm = np.linalg.norm(vec)
        return (vec / norm).tolist() if norm > 0 else vec.tolist()
        # .tolist() 把 numpy 数组转成普通 Python 列表（JSON 序列化需要）

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """批量嵌入多个文档块。"""
        return [self._vec(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        """嵌入单条查询。"""
        return self._vec(text)


# ── 单例模式 ──
# 整个程序只需要一个 Embedder 实例
_embedder: Optional[Embedder] = None


def get_embedder() -> Embedder:
    """获取全局唯一的 Embedder 实例。"""
    global _embedder
    if _embedder is None:
        _embedder = Embedder()
    return _embedder
