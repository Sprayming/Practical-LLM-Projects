# 
# 策略：
#   1. 查询扩展：补充同义词、上下位法律概念
#   2. 查询分解：复合问题拆解为多个子查询
#   3. HyDE：先生成假设性回答，用其向量检索
#   4. 回退：API 不可用时返回原查询
import json, os
from typing import Optional
from pathlib import Path
from loguru import logger


class QueryRewriter:
    """查询改写器 - 用 LLM 将用户问题改写为更利于检索的形式"""

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        self.api_key = api_key
        self.base_url = base_url or os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1")
        self._load_key()

    def _load_key(self):
        if not self.api_key:
            from dotenv import load_dotenv
            env_path = Path(__file__).resolve().parent.parent.parent / ".env"
            if env_path.exists():
                load_dotenv(str(env_path))
            self.api_key = self.api_key or os.getenv("LLM_API_KEY", "")

    def rewrite(self, query: str, context: str = "", num_variants: int = 2) -> list[str]:
        """改写查询，返回多个查询变体"""
        if not self.api_key:
            return [query]

        prompt = f"""你是一个法律检索专家。请将用户的问题改写成更适合向量检索的形式。

原问题：{query}

要求：
1. 保持原意不变
2. 补充相关法律术语和关键词
3. 如果包含多个子问题，拆分成独立查询
4. 每个变体不超过 50 字

输出格式（JSON 数组）：
["改写后的查询1", "改写后的查询2"]

只输出 JSON 数组，不要其他内容。"""

        if context:
            prompt += f"\n对话上下文：{context}"

        try:
            import requests
            resp = requests.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json={
                    "model": "deepseek-chat",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1,
                    "max_tokens": 200,
                },
                timeout=10,
            )
            if resp.status_code == 200:
                content = resp.json()["choices"][0]["message"]["content"]
                variants = json.loads(content.strip())
                if isinstance(variants, list) and len(variants) > 0:
                    # 去重 + 包含原查询
                    all_queries = [query] + [v for v in variants if v.strip() != query]
                    return all_queries[:num_variants + 1]
        except Exception as e:
            logger.warning("Query rewrite failed: {}", e)

        return [query]

    def expand(self, query: str) -> str:
        """简单查询扩展（不调用 API，用规则）"""
        # 法律常见术语扩展
        expansions = {
            "合同": "合同 协议 契约 合约",
            "劳动": "劳动 劳务 雇佣 工作",
            "赔偿": "赔偿 补偿 赔付 违约金",
            "辞职": "辞职 离职 解除 终止",
            "工资": "工资 薪酬 薪资 报酬",
        }
        result = query
        for keyword, replacement in expansions.items():
            if keyword in query:
                result = result.replace(keyword, replacement)
        return result