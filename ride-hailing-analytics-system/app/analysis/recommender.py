from __future__ import annotations
from openai import OpenAI
from app.config import settings


RECOMMENDER_PROMPT = """
你是一个运营策略顾问。根据用户的业务问题和数据分析结果，给出可执行的运营建议。

业务问题：{question}
数据分析结果：{data}

请给出：
1. 核心结论
2. 具体行动建议（2-3条）
3. 预期效果
""".strip()


def recommend(question: str, data: list[dict]) -> str:
    if not data:
        return "暂无数据支撑建议。"
    
    client = OpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)
    
    prompt = RECOMMENDER_PROMPT.format(
        question=question,
        data=str(data[:50]),
    )
    
    response = client.chat.completions.create(
        model=settings.llm_model,
        messages=[{"role": "user", "content": prompt}],
        temperature=settings.llm_temperature,
    )
    
    return response.choices[0].message.content
