from typing import Optional
from pydantic import BaseModel


class PlanStep(BaseModel):
    """单个计划步骤"""
    step_id: str
    agent_type: str  # data / analysis / suggest
    description: str
    sql_hint: str = ""
    depends_on: list[str] = []


class Plan(BaseModel):
    """完整的分析计划"""
    steps: list[PlanStep]
    reasoning: str = ""


def create_plan(question: str, api_key: str, base_url: str) -> Plan:
    """用 LLM 将用户问题拆解为可执行的步骤"""
    import requests, json

    prompt = f"""You are a data analysis planner for a ride-hailing platform.
Decompose the user's question into executable steps.

Available agent types:
- data: Executes SQL queries (providing sql_hint helps the SQL generator)
- analysis: Analyzes query results for patterns and root causes
- suggest: Generates business recommendations

Rules:
1. Each step must have a clear purpose
2. Analysis steps depend on data steps
3. Suggest steps depend on analysis steps
4. Keep steps focused and minimal

User question: {question}

Output JSON format:
{{
  "reasoning": "brief reason for this plan",
  "steps": [
    {{
      "step_id": "01", "agent_type": "data",
      "description": "query description",
      "sql_hint": "SELECT ...",
      "depends_on": []
    }}
  ]
}}
Return ONLY valid JSON, no other text."""

    try:
        resp = requests.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": "deepseek-chat", "messages": [{"role": "user", "content": prompt}], "temperature": 0.1},
            timeout=15,
        )
        if resp.status_code == 200:
            data = json.loads(resp.json()["choices"][0]["message"]["content"])
            return Plan(**data)
    except Exception:
        pass

    # Fallback: 默认三步计划
    return Plan(
        reasoning="Default plan (LLM unavailable)",
        steps=[
            PlanStep(step_id="01", agent_type="data", description=f"Query data for: {question}", sql_hint="", depends_on=[]),
            PlanStep(step_id="02", agent_type="analysis", description="Analyze the query results", depends_on=["01"]),
            PlanStep(step_id="03", agent_type="suggest", description="Generate recommendations", depends_on=["02"]),
        ]
    )
