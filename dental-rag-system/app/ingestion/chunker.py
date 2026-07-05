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
from loguru import logger              # 日志记录器，用于记录错误和调试信息 


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
    
# ============================================================
def get_tokenizer(model: str = "text-embedding-3-small") -> tiktoken.Encoding:
    """
    返回一个 token 编码器。
    
    Args:
        model (str): 模型名称，默认为 "text-embedding-3-small"
        
    Returns:
        tiktoken.Encoding: token 编码器
        
    Raises:
        ValueError: 如果无法获取有效的编码器
        
    Example:
        >>> tokenizer = get_tokenizer()
        >>> tokens = tokenizer.encode("Hello world")
        >>> len(tokens)
        2
    """
    try:
        return tiktoken.encoding_for_model(model) #使用 tiktoken 的 encoding_for_model 方法来获取指定模型的编码器
    except KeyError:
        try:
            return tiktoken.get_encoding("cl100k_base") #如果指定的模型不存在，就使用默认的编码器
        except Exception as e:
            raise ValueError(f"Failed to get tokenizer: {str(e)}")

def count_tokens(text: str, enc: tiktoken.Encoding) -> int:
    """
    返回文本中的 token 数量。
    
    Args:
        text (str): 要计算 token 数量的文本
        enc (tiktoken.Encoding): token 编码器
        
    Returns:
        int: 文本中的 token 数量
        
    Raises:
        ValueError: 如果文本或编码器无效
        
    Example:
        >>> tokenizer = get_tokenizer()
        >>> count_tokens("Hello world", tokenizer)
        2
    """
    if not text: #如果文本为空，就返回 0
        return 0
    if not enc: #如果编码器为空，就抛出异常
        raise ValueError("Encoder cannot be None") #如果编码器为空，就抛出异常
        
    try:
        return len(enc.encode(text))#使用编码器的 encode 方法将文本转换为 token 列表，然后返回列表的长度就是 token 数量了
    except Exception as e:# 如果转换过程中出现异常，就抛出异常
        raise ValueError(f"Failed to count tokens: {str(e)}")

# ============================================================
# def chunk_document(
#     doc: LoadedDocument,                # 待切分的文档
#     chunk_size: int = 800,              # 每块的目标 token 数
#     chunk_overlap: int = 200,           # 块间重叠 token 数
#     tokenizer: Optional[tiktoken.Encoding] = None,  # token 编码器
#     document_id: Optional[str] = None,  # 文档 ID（用于标记每个块属于哪个文档）
# )-> list[TextChunk]:
#     """把文档切分成多个文本块。"""
#     if tokenizer is None: #如果没有提供 token 编码器，就使用默认的编码器
#         tokenizer = get_tokenizer(doc.metadata.get("model", "text-embedding-3-small")) #使用文档的元信息中的 model 字段来选择合适的编码器，如果没有提供 model 字段，就使用默认的编码器

#     chunks: list[TextChunk] = [] #用于存储切分后的文本块
#     chunk_index = 0 #块索引，从0开始
    
#     for page in doc.pages: #遍历文档中的每一页
#         if not page.text.strip(): #如果页面的文本内容为空，就跳过这个页面
#             continue
#         page_number = page.page_number #获取页码
#         text = page.text #获取页面的文本内容
#         buffer = "" #用于缓存当前块的文本内容
#         buffer_token_count = 0 #用于缓存当前块的 token 数量

#         # 按段落切分
        
#         # paragraphs = text.split("\n") #按换行符切分文本，得到段落列表,这里属于硬切割，如果段落之间没有换行符，就会把整个文本当作一个段落
#         paragraphs = re.split(r"\n", text)#按换行符切分文本，得到段落列表，这里使用正则表达式，可以更灵活地处理换行符，比如可以处理多个连续的换行符
#         for para in paragraphs:
#             para = para.strip()# 去掉段落前后的空白字符
#             if not para: #如果段落为空，就跳过这个段落
#                 continue

#             para_token_count = count_tokens(para, tokenizer) #计算段落的 token 数量,需要看情况分类

#             # 情况1：如果当前这个段落，token 数量超过 chunk_size，就保存当前buffer块，并开始新的buffer块

#             if  para_token_count > chunk_size: #如果当前块的 token 数量加上段落的 token 数量超过了 chunk_size，就保存当前块，并开始新的块
#                 # 第一步先把 buffer 里攒的内容 flush 出去
#                 if buffer.strip(): #如果 buffer 不为空，就保存当前块
#                     chunks.append(TextChunk(
#                         content=buffer.strip(),
#                         chunk_index=chunk_index,
#                         page_number=page_number,
#                         document_id=document_id,
#                     ))
#                     chunk_index += 1 #块索引加1
#                 buffer = "" #清空 buffer
#                 buffer_token_count = 0 #清空 buffer 的 token 数量
               
#                 # 第二步段落按句子切分，并 flush 出去
#                 #情况1.1：如果当前段落切分出的句子，token 数量不超过 chunk_size，就保存当前buffer块，并开始新的buffer块
#                 # sentences = para.split("。") #按句号切分段落，得到句子列表
#                 sentences = re.split(r"(?<=[。！？])", para) #按句号、问号、感叹号切分段落，得到句子列表，这里使用正则表达式，可以更灵活地处理标点符号，比如可以处理中文和英文的标点符号
#                 for sent in sentences:
#                     sent = sent.strip() #去掉句子前后的空白字符
#                     if not sent: #如果句子为空，就跳过这个句子
#                         continue
#                     sent_token_count = count_tokens(sent, tokenizer) #计算句子的 token 数量

#                     if buffer_token_count + sent_token_count > chunk_size: #如果当前块的 token 数量加上句子的 token 数量超过了 chunk_size，就保存当前块，并开始新的块
#                         if buffer.strip(): #如果 buffer 不为空，就保存当前块
#                             chunks.append(TextChunk(
#                                 content=buffer.strip(),
#                                 chunk_index=chunk_index,
#                                 page_number=page_number,
#                                 document_id=document_id,
#                             ))
#                             chunk_index += 1 #块索引加1
#                         buffer = sent #将当前句子作为新块的开始
#                         buffer_token_count = sent_token_count #将当前句子的 token 数量作为新块的 token 数量
#                     else: #如果当前块的 token 数量加上句子的 token 数量没有超过 chunk_size，就将句子添加到当前块中
#                         if buffer: #如果当前块已经有内容了，就在块末尾添加一个换行符，然后再添加句子
#                             buffer += "\n" + sent
#                         else: #如果当前块还没有内容，就直接添加句子
#                             buffer = sent
#                         buffer_token_count += sent_token_count #更新当前块的 token 数量

#                         # 如果当前块还有内容，就保存它
#                         if buffer:#如果当前块还有内容，就保存它
#                             chunks.append(TextChunk(buffer, chunk_index, page_number, document_id)) #将当前块添加到 chunks 列表中
#                             chunk_index += 1
#                             buffer = "" #清空 buffer
#                             buffer_token_count = 0 #清空 buffer 的 token 数量
#                         continue #继续处理下一个页面下一段段落

#                     # 情况1.2：如果当前段落切分出的句子的token 数量超过 chunk_size
#                     # 第一步先把buffer里攒的内容flush出去
#                     if buffer.strip(): #如果buffer不为空，就保存当前块
#                         chunks.append(TextChunk(
#                             content=buffer.strip(),
#                             chunk_index=chunk_index,
#                             page_number=page_number,
#                             document_id=document_id,
#                         ))
#                         chunk_index += 1
#                     buffer = "" #清空buffer
#                     buffer_token_count = 0 #清空buffer的token数量

#                     # 第二步需要将句子继续按标点符号切分，并flush出去
#                     sentences = re.split(r"(?<=[。！？.!?])\s*", para) #按句号、问号、感叹号切分段落，得到句子列表
#                     for sentence_fragment in sentences:  # 使用sentence_fragment表示短句片段
#                         sentence_fragment = sentence_fragment.strip()
#                         if not sentence_fragment:
#                             continue
#                         fragment_token_count = count_tokens(sentence_fragment, tokenizer)  # 使用fragment_token_count表示短句片段的token计数
#                         if buffer_token_count + fragment_token_count > chunk_size:
#                             if buffer.strip():
#                                 chunks.append(TextChunk(
#                                     content=buffer.strip(),
#                                     chunk_index=chunk_index,
#                                     page_number=page_number,
#                                     document_id=document_id,
#                                 ))
#                                 chunk_index += 1
#                             buffer = sentence_fragment
#                             buffer_token_count = fragment_token_count
#                         else:
#                             if buffer:
#                                 buffer += "\n" + sentence_fragment
#                             else:
#                                 buffer = sentence_fragment
#                             buffer_token_count += fragment_token_count
#                     if buffer:
#                         chunks.append(TextChunk(
#                             content=buffer.strip(),
#                             chunk_index=chunk_index,
#                             page_number=page_number,
#                             document_id=document_id,
#                         ))
#                         chunk_index += 1
#                         buffer = ""
#                         buffer_token_count = 0

              
            

#             # 情况2： 正常段落:如果当前段落的 token 数量没有超过 chunk_size，就将段落添加到当前块中
#             #第一步：如果当前块加上当前这个段落，token 数量超过 chunk_size，就保存当前buffer块，并开始新的buffer块
#             if buffer_token_count + para_token_count > chunk_size: #如果当前块的 token 数量加上段落的 token 数量超过了 chunk_size，就保存当前块，并开始新的块
#                 if buffer.strip(): #如果 buffer 不为空，就保存当前块
#                     chunks.append(TextChunk(
#                         content=buffer.strip(),
#                         chunk_index=chunk_index,
#                         page_number=page_number,
#                         document_id=document_id,
#                     ))
#                     chunk_index += 1 #块索引加1

#                     # overlap：保留 buffer 末尾的 chunk_overlap 个 token
#                     tail_tokens = tokenizer.encode(buffer) #1.将 buffer 编码为 token 列表 
#                     if len(tail_tokens) > chunk_overlap: #2.如果 token 列表的长度大于 chunk_overlap，就保留最后 chunk_overlap 个 token
#                         tail_tokens = tail_tokens[-chunk_overlap:] #保留最后 chunk_overlap 个 token
#                     buffer = tokenizer.decode(tail_tokens) #3.将保留的 token 列表解码为字符串，作为新的 buffer
#                     buffer_token_count = len(tail_tokens) #4.更新 buffer 的 token 数量

#                 else: #如果 buffer 为空，就清空 buffer 和 buffer 的 token 数量
#                     buffer = ""
#                     buffer_token_count = 0

#             # 第二步：把当前段落加到 buffer 里
#             buffer = (buffer + "\n\n" + para).strip()
#             buffer_token_count = count_tokens(buffer, tokenizer) # 重新计算当前 buffer 的总 token 数

#         # 一页处理完 → flush 剩余 buffer
#         if buffer.strip(): #如果 buffer 不为空，就保存当前块
#             chunks.append(TextChunk(
#                 content=buffer.strip(),
#                 chunk_index=chunk_index,
#                 page_number=page_number,
#                 document_id=document_id,
#             ))
#             chunk_index += 1 #块索引加1
#             buffer = "" #清空 buffer
#             buffer_token_count = 0 #清空 buffer 的 token 数量

#     return chunks


class DocumentChunker:
    def __init__(self, chunk_size=1000, tokenizer=None):
        self.chunk_size = chunk_size
        self.tokenizer = tokenizer
        
    def _validate_document(self, document):
        """验证文档参数"""
        if not document:
            raise ValueError("Document cannot be empty")
        if not hasattr(document, 'full_text'): #如果文档没有 content 属性，就抛出 ValueError 异常
            raise ValueError("Document must have full_text attribute")
        if not hasattr(document, 'pages'): #如果文档没有 metadata 属性，就抛出 ValueError 异常
            raise ValueError("Document must have pages attribute")
            
    def _preprocess_content(self, content): #如果 content 为空，就返回一个空列表
        """预处理文档内容"""
        if not content:
            return []
        return content.split('\n\n')  # 按段落分割
        
    def _create_chunk(self, content, chunk_index, metadata): #如果 content 为空，就返回 None
        """创建文本块"""
        try:
            return TextChunk(
                content=content.strip(),
                chunk_index=chunk_index,
                page_number=metadata.get('page_number', 1),
                document_id=metadata.get('document_id', ''),
            )
        except Exception as e:
            print(f"Error creating chunk: {str(e)}")
            return None
            
    def _process_paragraph(self, para, buffer, buffer_token_count, chunks, chunk_index, page_number, document_id, chunk_size, tokenizer):
        # 情况1.2：如果当前段落切分出的句子的token 数量超过 chunk_size
        # 第一步先把 buffer 里攒的内容 flush 出去
        if buffer.strip(): 
            chunks.append(TextChunk(
                content=buffer.strip(),
                chunk_index=chunk_index,
                page_number=page_number,
                document_id=document_id,
            ))
            chunk_index += 1
            buffer = "" 
            buffer_token_count = 0 

        # 第二步需要将句子继续按标点符号切分
        sentences = re.split(r"(?<=[。！？.!?])\s*", para) 
        
        for sentence_fragment in sentences:  
            sentence_fragment = sentence_fragment.strip()
            if not sentence_fragment:
                continue
                
            fragment_token_count = count_tokens(sentence_fragment, tokenizer)  
            
            # 【关键修复】：处理单句超长的情况
            if fragment_token_count > chunk_size:
                # 策略二：允许超长，但必须独立成块
                # 1. 先把当前 buffer 里已有的内容 flush 出去（如果有）
                if buffer.strip():
                    chunks.append(TextChunk(
                        content=buffer.strip(),
                        chunk_index=chunk_index,
                        page_number=page_number,
                        document_id=document_id,
                    ))
                    chunk_index += 1
                    buffer = ""
                    buffer_token_count = 0
                
                # 2. 将这个超长的短句直接作为一个独立的块 flush 出去，绝不留在 buffer 里
                chunks.append(TextChunk(
                    content=sentence_fragment, # 超长句独立成块
                    chunk_index=chunk_index,
                    page_number=page_number,
                    document_id=document_id,
                ))
                chunk_index += 1
                # 注意：这里不更新 buffer，因为超长句已经被处理掉了，buffer 保持为空
                continue
                
            # 【正常情况下的逻辑】：短句没有超过 chunk_size
            if buffer_token_count + fragment_token_count > chunk_size:
                if buffer.strip():
                    chunks.append(TextChunk(
                        content=buffer.strip(),
                        chunk_index=chunk_index,
                        page_number=page_number,
                        document_id=document_id,
                    ))
                    chunk_index += 1
                buffer = sentence_fragment
                buffer_token_count = fragment_token_count
            else:
                if buffer:
                    buffer += "\n" + sentence_fragment
                else:
                    buffer = sentence_fragment
                buffer_token_count += fragment_token_count

        # 循环结束后，返回 buffer 和 chunk_index，交由外层主函数继续处理下一个段落
        # 注意：这里不再强制清空 buffer，因为 buffer 里的内容可能需要和下一段拼接
        return buffer, buffer_token_count, chunk_index

    



        

        
    def chunk(self, document):
        """主分块方法"""
        try:
            # 验证文档
            self._validate_document(document)
            
            # 初始化变量
            chunks = []
            chunk_index = 0
            buffer = ""
            buffer_token_count = 0
            metadata = document.metadata or {}
            
            # 预处理内容
            paragraphs = self._preprocess_content(document.full_text)
            
            # 处理每个段落
            for paragraph in paragraphs:
                if not paragraph.strip():#如果段落为空，就跳过
                    continue
                    
                # 处理段落
                page_number = metadata.get('page_number', 1)
                document_id = metadata.get('document_id', '')
                buffer, buffer_token_count, chunk_index = self._process_paragraph(
                    paragraph, buffer, buffer_token_count, chunks,
                    chunk_index, page_number, document_id,
                    self.chunk_size, self.tokenizer
                )
                
            # 处理剩余的buffer
            if buffer.strip():
                chunk = self._create_chunk(buffer, chunk_index, metadata)
                if chunk:
                    chunks.append(chunk)
                    
            return chunks
            
        except Exception as e:
            print(f"Error chunking document: {str(e)}")
            return []
