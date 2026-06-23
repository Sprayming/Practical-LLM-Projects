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
    
    for page in doc.pages: #遍历文档中的每一页
        if not page.text.strip(): #如果页面的文本内容为空，就跳过这个页面
            continue
        page_number = page.page_number #获取页码
        text = page.text #获取页面的文本内容
        buffer = "" #用于缓存当前块的文本内容
        buffer_token_count = 0 #用于缓存当前块的 token 数量

        # 按段落切分
        
        # paragraphs = text.split("\n") #按换行符切分文本，得到段落列表,这里属于硬切割，如果段落之间没有换行符，就会把整个文本当作一个段落
        paragraphs = re.split(r"\n", text)#按换行符切分文本，得到段落列表，这里使用正则表达式，可以更灵活地处理换行符，比如可以处理多个连续的换行符
        for para in paragraphs:
            para = para.strip()# 去掉段落前后的空白字符
            if not para: #如果段落为空，就跳过这个段落
                continue

            para_token_count = count_tokens(para, tokenizer) #计算段落的 token 数量,需要看情况分类

            # 情况1：如果当前这个段落，token 数量超过 chunk_size，就保存当前buffer块，并开始新的buffer块

            if  para_token_count > chunk_size: #如果当前块的 token 数量加上段落的 token 数量超过了 chunk_size，就保存当前块，并开始新的块
                # 第一步先把 buffer 里攒的内容 flush 出去
                if buffer.strip(): #如果 buffer 不为空，就保存当前块
                    chunks.append(TextChunk(
                        content=buffer.strip(),
                        chunk_index=chunk_index,
                        page_number=page_number,
                        document_id=document_id,
                    ))
                    chunk_index += 1 #块索引加1
                buffer = "" #清空 buffer
                buffer_token_count = 0 #清空 buffer 的 token 数量
               
                # 第二步段落按句子切分，并 flush 出去
                #情况1.1：如果当前段落切分出的句子，token 数量不超过 chunk_size，就保存当前buffer块，并开始新的buffer块
                # sentences = para.split("。") #按句号切分段落，得到句子列表
                sentences = re.split(r"(?<=[。！？])", para) #按句号、问号、感叹号切分段落，得到句子列表，这里使用正则表达式，可以更灵活地处理标点符号，比如可以处理中文和英文的标点符号
                for sent in sentences:
                    sent = sent.strip() #去掉句子前后的空白字符
                    if not sent: #如果句子为空，就跳过这个句子
                        continue
                    sent_token_count = count_tokens(sent, tokenizer) #计算句子的 token 数量

                    if buffer_token_count + sent_token_count > chunk_size: #如果当前块的 token 数量加上句子的 token 数量超过了 chunk_size，就保存当前块，并开始新的块
                        if buffer.strip(): #如果 buffer 不为空，就保存当前块
                            chunks.append(TextChunk(
                                content=buffer.strip(),
                                chunk_index=chunk_index,
                                page_number=page_number,
                                document_id=document_id,
                            ))
                            chunk_index += 1 #块索引加1
                        buffer = sent #将当前句子作为新块的开始
                        buffer_token_count = sent_token_count #将当前句子的 token 数量作为新块的 token 数量
                    else: #如果当前块的 token 数量加上句子的 token 数量没有超过 chunk_size，就将句子添加到当前块中
                        if buffer: #如果当前块已经有内容了，就在块末尾添加一个换行符，然后再添加句子
                            buffer += "\n" + sent
                        else: #如果当前块还没有内容，就直接添加句子
                            buffer = sent
                        buffer_token_count += sent_token_count #更新当前块的 token 数量

                # 如果当前块还有内容，就保存它
                if buffer:#如果当前块还有内容，就保存它
                    chunks.append(TextChunk(buffer, chunk_index, page_number, document_id)) #将当前块添加到 chunks 列表中
                    chunk_index += 1
                    buffer = "" #清空 buffer
                    buffer_token_count = 0 #清空 buffer 的 token 数量
                continue #继续处理下一个页面下一段段落

                # 情况1.2：如果当前段落切分出的句子的token 数量超过 chunk_size
                # 第一步先把 buffer 里攒的内容 flush 出去
                if buffer.strip(): #如果 buffer 不为空，就保存当前块
                    chunks.append(TextChunk(
                        content=buffer.strip(),
                        chunk_index=chunk_index,
                        page_number=page_number,
                        document_id=document_id,
                    ))
                    chunk_index += 1
                buffer = "" #清空 buffer
                buffer_token_count = 0 #清空 buffer 的 token 数量

                # 第二步需要将句子继续按标点符号切分，并 flush 出去
                kids = re.split(r"(?<=[。！？.!?])\s*", para) #按句号、问号、感叹号切分段落，得到句子列表，这里使用正则表达式，可以更灵活地处理标点符号，比如可以处理中文和英文的标点符号
                for kid in kids: #按句号、问号、感叹号切分段落，得到句子列表，这里使用正则表达式，可以更灵活地处理标点符号，比如可以处理中文和英文的标点符号
                    kid = kid.strip()
                    if not kid:
                        continue
                    kid_token_count = count_tokens(kid, tokenizer)
                    if buffer_token_count + kid_token_count > chunk_size:
                        if buffer.strip():
                            chunks.append(TextChunk(
                                content=buffer.strip(),
                                chunk_index=chunk_index,
                                page_number=page_number,
                                document_id=document_id,
                            ))
                            chunk_index += 1
                        buffer = kid
                        buffer_token_count = kid_token_count
                    else:
                        if buffer:
                            buffer += "\n" + kid
                        else:
                            buffer = kid
                        buffer_token_count += kid_token_count
                if buffer:
                    chunks.append(TextChunk(buffer, chunk_index, page_number, document_id))
                    chunk_index += 1
                    buffer = ""
                    buffer_token_count = 0
                continue

            

            # 情况2： 正常段落:如果当前段落的 token 数量没有超过 chunk_size，就将段落添加到当前块中
            #第一步：如果当前块加上当前这个段落，token 数量超过 chunk_size，就保存当前buffer块，并开始新的buffer块
            if buffer_token_count + para_token_count > chunk_size: #如果当前块的 token 数量加上段落的 token 数量超过了 chunk_size，就保存当前块，并开始新的块
                if buffer.strip(): #如果 buffer 不为空，就保存当前块
                    chunks.append(TextChunk(
                        content=buffer.strip(),
                        chunk_index=chunk_index,
                        page_number=page_number,
                        document_id=document_id,
                    ))
                    chunk_index += 1 #块索引加1

                    # overlap：保留 buffer 末尾的 chunk_overlap 个 token
                    tail_tokens = tokenizer.encode(buffer) #1.将 buffer 编码为 token 列表 
                    if len(tail_tokens) > chunk_overlap: #2.如果 token 列表的长度大于 chunk_overlap，就保留最后 chunk_overlap 个 token
                        tail_tokens = tail_tokens[-chunk_overlap:] #保留最后 chunk_overlap 个 token
                    buffer = tokenizer.decode(tail_tokens) #3.将保留的 token 列表解码为字符串，作为新的 buffer
                    buffer_token_count = len(tail_tokens) #4.更新 buffer 的 token 数量

                else: #如果 buffer 为空，就清空 buffer 和 buffer 的 token 数量
                    buffer = ""
                    buffer_token_count = 0

            # 第二步：把当前段落加到 buffer 里
            buffer = (buffer + "\n\n" + para).strip()
            buffer_token_count = count_tokens(buffer, tokenizer) # 重新计算当前 buffer 的总 token 数

        # 一页处理完 → flush 剩余 buffer
        if buffer.strip(): #如果 buffer 不为空，就保存当前块
            chunks.append(TextChunk(
                content=buffer.strip(),
                chunk_index=chunk_index,
                page_number=page_number,
                document_id=document_id,
            ))
            chunk_index += 1 #块索引加1
            buffer = "" #清空 buffer
            buffer_token_count = 0 #清空 buffer 的 token 数量

    return chunks
