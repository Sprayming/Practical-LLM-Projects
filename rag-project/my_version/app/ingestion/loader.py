# ============================================================
# 文档加载器 — 把各种格式的文件解析成纯文本
# 支持：PDF、DOCX、TXT、Markdown
# 输出：LoadedDocument 对象（包含按页的文本内容）
# ============================================================


#导入依赖包
from pathlib import Path
from typing import Optional #可选类型，表示参数可以是某种类型或 None
from logur import logger

from __future__ import annotations #允许在类定义中引用自身

#定义 Documentpage 类，表示加载后显示的文档
class DocumentPage:
    def __init__(self, content: str, page_number: int):
        self.content = content
        self.page_number = page_number #页码，从1开始

#定义 LoadedDocument 类，表示加载的文档
class LoadedDocument:
    def __init__(
        self,#先写注释
        pages: List[DocumentPage], #文档的页列表，每页是一个 DocumentPage 对象
        file_path: str, #文档的原始文件路径
        filename: str,  #文档的文件名
        metadata: Optional[dict] = None,
        ) ->None:#文档的元信息，可以是任何键值对，默认为 None
        self.pages = pages
        self.file_path = file_path
        self.filename = filename
        self.metadata = metadata or {} #如果没有提供元信息，就用一个空字典

    @property
    def full_text(self) -> str:
        """把所有页的文本拼成一段。"""
        return "\n".join(p.content for p in self.pages)
    
    @property
    def char_count(self) -> int:
        """计算总的字符数"""
        return sum(len(p.content) for p in self.pages)

    @property
    def page_count(self) -> int:
        """计算总的页数"""
        return len(self.pages)
    
#定义 Loader 类，表示文档加载器
class Load_document:
    #根据文件后缀名自动选择加载器
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.filename = Path(file_path).name #从路径中提取文件名
        self.pages = [] #初始化页列表为空


