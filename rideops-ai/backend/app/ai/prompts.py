"""
提示词模板 — 运营分析 + 问答
"""

SYSTEM_PROMPT = """你是一个专业的网约车运营数据分析师。
请基于提供的运营数据，回答用户的问题。

## 回答原则
1. **数据驱动**：所有结论必须有数据支撑，不能凭空推测
2. **业务导向**：分析要能指导实际运营决策
3. **简洁清晰**：直接回答问题，突出关键数据
4. **中文回答**：默认用中文输出

## 可分析的内容
- 运营整体状况（订单量、收入、完成率等）
- 趋势变化（增长/下降）
- 异常点（波动较大的指标）
- 司机绩效（接单量、收入、评分）
- 时段分析（早高峰、晚高峰）
"""


def build_qa_prompt(query: str, context_data: str) -> list[dict]:
    """构建问答提示词

    参数：
        query: 用户的问题
        context_data: 当前数据的分析摘要（KPI、趋势、异常等）
    """
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"""
## 当前运营数据
{context_data}

## 用户问题
{query}

请基于上述数据回答用户的问题，引用具体的数据指标来支撑你的回答。
""",
        },
    ]


def build_analysis_prompt(
    stats_summary: str,
    trend_data: str,
    anomaly_data: str,
    user_query: str = "",
) -> list[dict]:
    """构建完整分析提示词"""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"""
## 运营数据概览
{stats_summary}

## 趋势数据
{trend_data}

## 异常检测结果
{anomaly_data}

## {'用户问题' if user_query else '分析需求'}
{user_query if user_query else '请全面分析上述运营数据，给出洞察和建议'}
""",
        },
    ]
