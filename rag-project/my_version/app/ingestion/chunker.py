# ============================================================
# 文本分块器 — 把长文档切成适合 LLM 处理的小块
# 
# 为什么需要分块：
#   · LLM 有上下文窗口限制（DeepSeek 64K，但塞满又贵又慢）
#   · 不是整篇文档都相关，只给 LLM 最相关的那几段就好
#   · 块之间要有重叠，避免"刚好切丢了关键信息"
#
# 策略：按段落切 → 段落太长按句子切
# 用 tiktoken 数 token 而不是 len()，因为中文一个字可能=1~2 token
# ============================================================

from __future__ import annotations

from typing import  Optional
from .loader import LoadedDocument     # 父级目录的 loader 模块
import re                              # 正则表达式，用于按标点切分句子
import tiktoken                        # OpenAI 的 token 计数器


class TextChunk: #这个类表示一个文本块，包含内容、块索引、来源页码和文档 ID，标注化了文本块的基本信息，方便后续处理和追踪
    """单个文本块。"""
    def __init__(
        self,
        content: str,                   # 本块的文本内容
        chunk_index: int,              # 块的序号
        page_number: Optional[int] = None,  # 来源页码
        document_id: Optional[str] = None,  # 来源文档 ID
    ) -> None:
        self.content = content
        self.chunk_index = chunk_index
        self.page_number = page_number
        self.document_id = document_id

def get_tokenizer(model: str = "text-embedding-3-small") -> tiktoken.Encoding: #这个函数返回一个 token 编码器，用于计算文本中的 token 数量
    """返回一个 token 编码器。"""
    try: #需要做异常处理，因为如果模型名称不认识，tiktoken 会抛出 KeyError，这时我们回退到一个默认的编码器 cl100k_base，这样就能保证函数总是返回一个有效的编码器了
        return tiktoken.encoding_for_model(model) #根据模型名称返回对应的 token 编码器
    except KeyError:
        return tiktoken.get_encoding("cl100k_base") #如果模型名称不认识，就回退到 cl100k_base
    

def count_tokens(text: str, enc: tiktoken.Encoding) -> int: #这个函数返回文本中的 token 数量
    """返回文本中的 token 数量。"""
    return len(enc.encode(text)) #使用编码器的 encode 方法将文本转换为 token 列表，然后返回列表的长度就是 token 数量了


def chunk_document(
    doc: LoadedDocument,                # 待切分的文档
    chunk_size: int = 800,              # 每块的目标 token 数
    chunk_overlap: int = 200,           # 块间重叠 token 数
    tokenizer: Optional[tiktoken.Encoding] = None,  # token 编码器
    document_id: Optional[str] = None,  # 文档 ID（用于标记每个块属于哪个文档）
)-> list[TextChunk]:
    """把文档切分成多个文本块。"""
    if tokenizer is None: #如果没有提供 token 编码器，就使用默认的编码器
        tokenizer = get_tokenizer(doc.metadata.get("model", "text-embedding-3-small")) #使用文档的元信息中的 model 字段来选择合适的编码器，如果没有提供 model 字段，就使用默认的编码器

    chunks: list[TextChunk] = [] #用于存储切分后的文本块
    chunk_index = 0 #块索引，从0开始
    