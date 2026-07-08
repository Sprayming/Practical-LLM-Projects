from typing import Optional
from app.config import settings
from app.ai.prompts import build_qa_prompt


class AIAnalyst:
    def __init__(self):
        self._available = bool(settings.llm_api_key)
        if self._available:
            from openai import OpenAI
            self._client = OpenAI(
                api_key=settings.llm_api_key,
                base_url=settings.llm_base_url,
            )
            self._model = settings.llm_model
            self._temperature = settings.llm_temperature

    def _call_llm(self, messages: list[dict]) -> str:
        """调用 LLM 生成回答"""
        if not self._available:
            return "请配置 LLM_API_KEY 后使用 AI 功能"
        try:
            resp = self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=self._temperature,
            )
            return resp.choices[0].message.content or ""
        except Exception as e:
            return f"AI 调用失败: {e}"

    def ask_question(self, query: str, context_data: str) -> str:
        """回答用户的自然语言问题"""
        messages = build_qa_prompt(query, context_data)
        return self._call_llm(messages)

    def generate_analysis(
        self,
        stats_summary: str,
        trend_data: str,
        anomaly_data: str,
        user_query: str = "请全面分析上述运营数据，给出洞察和建议",
    ) -> str:
        """生成完整运营分析"""
        from app.ai.prompts import build_analysis_prompt
        messages = build_analysis_prompt(stats_summary, trend_data, anomaly_data, user_query)
        return self._call_llm(messages)


_analyst: Optional[AIAnalyst] = None


def get_analyst() -> AIAnalyst:
    global _analyst
    if _analyst is None:
        _analyst = AIAnalyst()
    return _analyst
