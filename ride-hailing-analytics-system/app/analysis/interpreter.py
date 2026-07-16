from __future__ import annotations
from openai import OpenAI
from app.config import settings


INTERPRETER_PROMPT = """
你是一个数据分析师。根据用户的原始问题和 SQL 查询结果，给出数据解读。

数据：
{data}

原始问题：{question}

请从以下角度分析：
1. 数据概况：关键指标和趋势
2. 业务洞察：这些数据说明了什么问题
3. 异常发现：是否有需要关注的反常数据
""".strip()


def interpret(question: str, sql: str, rows: list[dict]) -> str:
    if not rows:
        return "查询未返回数据，请检查问题是否准确。"
    
    client = OpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)
    
    prompt = INTERPRETER_PROMPT.format(
        question=question,
        data=str(rows[:50]),
    )
    
    response = client.chat.completions.create(
        model=settings.llm_model,
        messages=[{"role": "user", "content": prompt}],
        temperature=settings.llm_temperature,
    )
    
    return response.choices[0].message.content
