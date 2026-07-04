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
#这个词嵌入是用哈希计算，基于哈希的词袋模型做的
# ============================================================

from __future__ import annotations # 允许在函数定义前使用返回类型

import hashlib

from typing import Optional

import numpy as np

from loguru import logger

from app.config import settings #导入配置文件

import jieba


class Embedder:
    """把中文文本转成向量（数字数组）"""    
    def __init__(self, dim：int | None = None):#初始化方法
        self.dim = dim or settings.EMBEDDING_DIM #如果dim为空，则使用配置文件中的EMBEDDING_DIM
        
        self._jieba= jieba #jieba分词器

        logger.info("Embedder ready: jieba + ngram, dim={}", self.dim)

    def _vec(self, text: str) -> np.ndarray:
        """把文本转成向量"""
        # 第一层：词语级别的特征分词（权重为 1）
        vec = np.zeros(self.dim, dtype=np.float32) #初始化向量
        for word in self._jieba.cut(text): #用jieba分词
            word = word.strip() #去掉空格
            if not word: #如果词为空，则跳过
                continue
                
            # 哈希映射
            h = int.from_bytes(hashlib.md5(word.encode()).digest()[:4], "little") % self.dim #用MD5哈希映射到向量位置
            vec[h] += 1 #向量对应位置加1


        # 第二层：字符级别的特征分词（权重为 0.1）
        for i in range(len(text) - 1): #遍历文本
            h = int.from_bytes(hashlib.md5(text[i:i+2].encode()).digest()[:4], "little") % self.dim #用MD5哈希映射到向量位置
            vec[h] += 0.3#向量对应位置加0.3

        # 归一化
        norm = np.linalg.norm(vec) #计算向量长度
        return (vec / norm).tolist() if norm != 0 else vec.tolist() #如果向量长度不为0，则归一化，否则返回原向量
    

     def embed_document(self,texts: list[str]) -> list[list[float]]:
        """把文档列表转成向量列表"""
        return [self._vec(text) for text in texts] #遍历文本列表，用_vec方法转成向量
    
     def embed_query(self, text: str) -> list[float]:
        """把查询转成向量"""
        return self._vec(text) #用_vec方法转成向量,单条查询直接调用_vec方法
    

    #单例模式
    #整个程序都只需要一个实例
    _embedder: Optional[Embedder] = None


    def get_embedder() -> Embedder:
        """获取嵌入服务实例"""
        global _embedder
        if Embedder._embedder is None:
            Embedder._embedder = Embedder()
        return Embedder._embedder
    

        





