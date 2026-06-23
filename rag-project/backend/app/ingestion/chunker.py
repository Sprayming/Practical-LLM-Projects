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

import re                              # 正则表达式，用于按标点切分句子
from typing import Optional

import tiktoken                        # OpenAI 的 token 计数器

from .loader import LoadedDocument     # 父级目录的 loader 模块


class TextChunk:
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


def get_tokenizer(model: str = "text-embedding-3-small") -> tiktoken.Encoding:
    """获取 tiktoken 编码器。
    
    嵌入模型用的是 text-embedding-3-small，
    它的 tokenizer 是 cl100k_base。
    如果这个模型名不认识，就回退到 cl100k_base。
    """
    try:
        return tiktoken.encoding_for_model(model)
    except KeyError:
        return tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str, enc: tiktoken.Encoding) -> int:
    """计算一段文本的 token 数量。"""
    return len(enc.encode(text))


def chunk_document(
    doc: LoadedDocument,                # 待切分的文档
    chunk_size: int = 800,              # 每块的目标 token 数
    chunk_overlap: int = 200,           # 块间重叠 token 数
    tokenizer: Optional[tiktoken.Encoding] = None,  # token 编码器
    document_id: Optional[str] = None,  # 文档 ID（用于标记每个块属于哪个文档）
) -> list[TextChunk]:
    """主分块函数。把文档按页→段落→句子逐级切分。"""
    if tokenizer is None:
        tokenizer = get_tokenizer()  # 没传就用默认的

    chunks: list[TextChunk] = []
    idx = 0  # 块的全局序号

    for page in doc.pages:  # 逐页处理
        if not page.text.strip():
            continue  # 空页跳过

        # 按空行切分成段落
        paragraphs = re.split(r"\n\s*\n", page.text)
        buffer = ""        # 当前正在累积的块
        buf_tokens = 0     # buffer 的 token 数

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            para_tokens = count_tokens(para, tokenizer)

            # ── 情况1：单个段落就超过了 chunk_size ──
            # 这种超长段落需要按句子切成更小的片段
            if para_tokens > chunk_size:
                # 先把 buffer 里攒的内容 flush 出去
                if buffer.strip(): # buffer 不为空
                    chunks.append(TextChunk(
                        content=buffer.strip(),
                        chunk_index=idx,
                        page_number=page.page_number,
                        document_id=document_id,
                    ))
                    idx += 1
                buffer = ""
                buf_tokens = 0

                # 对这个超长段落按句子切分
                sentences = re.split(r"(?<=[。！？.!?])\s*", para)
                for sent in sentences:
                    sent = sent.strip()
                    if not sent:
                        continue
                    st = count_tokens(sent, tokenizer)
                    # 如果加入这个句子会超 chunk_size，先 flush 当前 buffer
                    if buf_tokens + st > chunk_size and buffer:
                        chunks.append(TextChunk(
                            content=buffer.strip(),
                            chunk_index=idx,
                            page_number=page.page_number,
                            document_id=document_id,
                        ))
                        idx += 1
                        # overlap：保留 buffer 末尾的 chunk_overlap 个 token
                        tail_tokens = tokenizer.encode(buffer)
                        if len(tail_tokens) > chunk_overlap:
                            tail_tokens = tail_tokens[-chunk_overlap:]
                        buffer = tokenizer.decode(tail_tokens)
                        buf_tokens = len(tail_tokens)

                    buffer = (buffer + " " + sent).strip()
                    buf_tokens = count_tokens(buffer, tokenizer)

                # 处理完段落，flush 剩余
                if buffer.strip():
                    chunks.append(TextChunk(
                        content=buffer.strip(),
                        chunk_index=idx,
                        page_number=page.page_number,
                        document_id=document_id,
                    ))
                    idx += 1
                    buffer = ""
                    buf_tokens = 0
                continue  # 处理下一个段落

            # ── 情况2：正常段落 ──
            # 如果加入当前段落会超 chunk_size，先 flush buffer
            if buf_tokens + para_tokens > chunk_size and buffer:
                chunks.append(TextChunk(
                    content=buffer.strip(),
                    chunk_index=idx,
                    page_number=page.page_number,
                    document_id=document_id,
                ))
                idx += 1
                # 保留 overlap 用于下一个块
                tail_tokens = tokenizer.encode(buffer)
                if len(tail_tokens) > chunk_overlap:
                    tail_tokens = tail_tokens[-chunk_overlap:]
                buffer = tokenizer.decode(tail_tokens)
                buf_tokens = len(tail_tokens)

            # 把当前段落加到 buffer 里
            buffer = (buffer + "\n\n" + para).strip()
            buf_tokens = count_tokens(buffer, tokenizer)

        # 一页处理完 → flush 剩余 buffer
        if buffer.strip():
            chunks.append(TextChunk(
                content=buffer.strip(),
                chunk_index=idx,
                page_number=page.page_number,
                document_id=document_id,
            ))
            idx += 1

    return chunks
