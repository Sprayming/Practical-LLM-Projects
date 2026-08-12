# 
# 流程:
#   检索时记录每个 chunk 的来源信息
#   → 拼上下文时附带来源标记 [来源: filename]
#   → AI 回答后提取实际引用的来源
#   → 返回结构化引用列表

"""
citation —— 法律文档引用来源追踪与引用生成。

【作用与功能】
在检索与生成阶段记录每个 chunk 的来源 metadata(文件名、页码、chunk 索引等)，
为上下文拼接附带来源标记，并在 AI 回答后提取其实际引用的来源编号，
最终输出结构化引用列表，支撑可溯源的法律问答。

【主要组成】
- `Source`:单条引用来源的 dataclass
- `CitationResult`:引用结果(答案 + 来源列表 + 格式化文本)
- `CitationTracker`:来源收集、上下文标记、引用列表与编号提取

【适用场景】
- 场景1:检索后收集各文档 chunk 来源，拼装带 [n] 标记的上下文
- 场景2:生成后从回答中提取 [n] 编号，输出去重参考来源清单

【依赖关系】
- 上游调用方:RAG 问答流水线
- 下游依赖:langchain Document、loguru
"""
from typing import Optional
from dataclasses import dataclass, field
from datetime import datetime
from loguru import logger


@dataclass
class Source:
    """单个引用来源"""
    document_id: str = ""
    filename: str = ""
    page_number: Optional[int] = None
    chunk_index: int = 0
    content: str = ""
    score: float = 0.0


@dataclass
class CitationResult:
    """引用结果"""
    answer: str = ""
    sources: list[Source] = field(default_factory=list)
    formatted_sources: str = ""


class CitationTracker:
    """引用追踪器 - 记录检索到的来源并生成引用"""

    def __init__(self):
        """初始化引用追踪器，建立来源列表。"""
        self._sources: list[Source] = []

    def add_source(self, source: Source):
        """添加一个检索来源"""
        self._sources.append(source)

    def add_sources(self, documents: list, scores: Optional[list[float]] = None):
        """从检索结果添加来源"""
        for i, doc in enumerate(documents):
            meta = doc.metadata if hasattr(doc, "metadata") else {}
            self._sources.append(Source(
                content=doc.page_content[:200] if hasattr(doc, "page_content") else str(doc)[:200],
                score=scores[i] if scores and i < len(scores) else 0.0,
                filename=meta.get("source", meta.get("filename", "未知来源")),
                page_number=meta.get("page_number"),
                chunk_index=meta.get("chunk_index", i),
                document_id=meta.get("document_id", f"src_{i}"),
            ))

    def format_context(self) -> str:
        """生成带来源标记的上下文文本"""
        parts = []
        for i, src in enumerate(self._sources):
            marker = f"[{i + 1}]"
            ref = f"{src.filename}"
            if src.page_number:
                ref += f" 第{src.page_number}页"
            parts.append(f"{marker} {ref}\n{src.content}")
        return "\n\n".join(parts)

    def format_citations(self) -> str:
        """生成引用列表文本"""
        if not self._sources:
            return ""
        lines = ["\n\n---\n**参考来源:**"]
        seen = set()
        for src in self._sources:
            key = f"{src.filename}:{src.page_number}"
            if key not in seen:
                seen.add(key)
                ref = f"- {src.filename}"
                if src.page_number:
                    ref += f" (第{src.page_number}页)"
                lines.append(ref)
        return "\n".join(lines)

    def extract_answer_citations(self, answer: str) -> list[str]:
        """从 AI 回答中提取引用的来源编号"""
        import re
        return re.findall(r'\[(\d+)\]', answer)

    def get_sources(self) -> list[Source]:
        """返回当前收集到的全部引用来源列表。"""
        return self._sources

    def clear(self):
        """清空已收集的来源列表，准备新一轮追踪。"""
        self._sources.clear()