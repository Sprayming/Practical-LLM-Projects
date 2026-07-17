import json, requests


class AnalysisTool:
    def __init__(self, api_key: str = "", base_url: str = ""):
        self.api_key = api_key
        self.base_url = base_url or "https://api.deepseek.com/v1"

    def analyze(self, step, question: str, context: dict, all_results: dict) -> dict:
        data_text = ""
        for k, v in all_results.items():
            if isinstance(v, dict) and "rows" in v:
                data_text += f"\\nStep {k}: {json.dumps(v['rows'][:5], ensure_ascii=False, default=str)}"

        prompt = f"""Analyze these query results to answer the user's question.

Question: {question}
Data: {data_text}

Provide:
1. Key findings
2. Root causes
3. Notable patterns"""

        try:
            resp = requests.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json={"model": "deepseek-chat", "messages": [{"role": "user", "content": prompt}], "temperature": 0.1},
                timeout=30,
            )
            if resp.status_code == 200:
                analysis = resp.json()["choices"][0]["message"]["content"]
                return {"type": "analysis", "analysis": analysis}
        except Exception as e:
            return {"type": "analysis", "error": str(e)}

        return {"type": "analysis", "analysis": "Analysis unavailable"}
