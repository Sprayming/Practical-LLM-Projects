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

from teaching.config import settings
from teaching.models import CitationSource
from teaching.generation.prompt_templates import build_qa_prompt  # 提示词模板


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
        self.model = model or settings.llm_model
        self.temperature = temperature if temperature is not None else settings.llm_temperature
        self.max_tokens = max_tokens or settings.llm_max_tokens
        
        # 创建 OpenAI 客户端（指向 DeepSeek 的地址）
        # DeepSeek 的 API 兼容 OpenAI 的格式
        self._client = OpenAI(
            api_key=api_key or settings.llm_api_key,
            base_url=base_url or settings.llm_base_url,
        )

    def generate(
        self,
        query: str,                     # 用户问题
        sources: list[CitationSource],   # 检索到的相关文本块
    ) -> tuple[str, int]:
        """生成回答。
        
        1. 把检索到的文本块格式化为上下文
        2. 拼成 Prompt 发送给 DeepSeek
        3. 返回回答文本 + 消耗的 token 数
        """
        # 把引用来源格式化为上下文文本
        context = self._format_context(sources)
        # 构建完整的 Prompt（system + user 消息）
        messages = build_qa_prompt(query, context)

        logger.info("LLM call: model={}, sources={}", self.model, len(sources))
        
        # 调用 DeepSeek API
        resp = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        
        answer = resp.choices[0].message.content or ""
        tokens = resp.usage.total_tokens if resp.usage else 0
        return answer, tokens

    def _format_context(self, sources: list[CitationSource]) -> str:
        """把引用来源格式化为 LLM 可读的上下文。
        
        格式：
            === 参考资料 1 ===
            来源: 文件名 (第X页)
            原文内容...
        """
        parts = []
        for i, s in enumerate(sources, 1):
            ref = f"[{i}] {s.filename}"
            if s.page_number:
                ref += f" (第{s.page_number}页)"
            parts.append(f"=== 参考资料 {i} ===\n来源: {ref}\n{s.content}")
        return "\n\n".join(parts)


# ── 单例 ──
_llm: Optional[LLMService] = None


def get_llm() -> LLMService:
    global _llm
    if _llm is None:
        _llm = LLMService()
    return _llm
