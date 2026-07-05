# ============================================================
# LLM 服务 — 调用 DeepSeek API 生成回答
#
# 把检索到的文本块 + 用户问题 拼成 Prompt
# 发给 DeepSeek，拿到回答
# ============================================================


from __future__ import annotations

from typing import Optional

from loguru import logger
from openai import OpenAI                         # OpenAI SDK 兼容 DeepSeek API

from app.config import settings
from app.models import CitationSource
from app.generation.prompt_templates import build_qa_prompt  # 提示词模板


class LLMService:
    """大模型服务。用 DeepSeek API 生成回答。"""

    def __init__(
        self,
        api_key: Optional[str] = None,    # DeepSeek API Key
        base_url: Optional[str] = None,   # API 地址
        model: Optional[str] = None,      # 模型名
        temperature: float = 0.15,        # 生成温度
        max_tokens: int = 2048,           # 最大输出 token

    ) -> None:
        self.api_key = api_key or settings.DEEPSEEK_API_KEY
        self.base_url = base_url or settings.DEEPSEEK_API_URL
        self.model = model or settings.DEEPSEEK_MODEL
        self.temperature = temperature
        self.max_tokens = max_tokens

        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)  # DeepSeek API 客户端

    def generate(
        self,
        query: str,                     # 用户问题
        sources: list[CitationSource],   # 检索到的相关文本块
    ) -> tuple[str, int]:
        """生成回答。

        Args:
            1、query (str): 用户问题
            2、sources (list[CitationSource]): 检索到的相关文本块

        Returns:
            1、answer (str): 回答
            2、token_count (int): 使用的 token 数量
        """
        # 1. 把检索到的文本块 + 用户问题 拼成 Prompt
        context = self._format_context(sources)
        prompt = build_qa_prompt(query, context)

        logger.info("LLM call: model={}, sources={}", self.model, len(sources))

        # 2. 调用 DeepSeek API 生成回答
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )

        answer = response.choices[0].message.content
        token_count = response.usage.total_tokens
        return answer, token_count
    
    def _format_context(self, sources: list[CitationSource]) -> str:
        """
        把引用来源格式化为 LLM 可读的上下文。
        
        格式：
            === 参考资料 1 ===
            来源: 文件名 (第X页)
            原文内容...
        """
        text=[]
        for i, s in enumerate(sources):
            ref = f"=== 参考资料 {i} ===\n来源: {s.source} ({s.page})\n{s.text}\n"
            if s.page_number:
                ref += f"第 {s.page_number} 页\n"
            text.append(f"=== 参考资料 {i} ===\n来源: {ref}\n{s.content}")
        return "\n\n".join(text)

        

#单例
_llm:Optional[LLMService] = None

def get_llm() -> LLMService:
    global _llm
    if not _llm:
        _llm = LLMService()
    return _llm