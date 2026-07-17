import json, requests


class ReportTool:
    def __init__(self, api_key: str = "", base_url: str = ""):
        self.api_key = api_key
        self.base_url = base_url or "https://api.deepseek.com/v1"

    def generate(self, step, question: str, all_results: dict) -> dict:
        results_text = json.dumps(
            {k: v for k, v in all_results.items() if isinstance(v, dict)},
            ensure_ascii=False, default=str, indent=2
        )

        prompt = f"""Based on the analysis results, generate a business recommendation report.

Question: {question}
Results: {results_text}

Provide:
1. Executive summary
2. Actionable recommendations (2-3 items)
3. Expected impact"""

        try:
            resp = requests.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json={"model": "deepseek-chat", "messages": [{"role": "user", "content": prompt}], "temperature": 0.1},
                timeout=30,
            )
            if resp.status_code == 200:
                report = resp.json()["choices"][0]["message"]["content"]
                return {"type": "suggest", "report": report}
        except Exception as e:
            return {"type": "suggest", "error": str(e)}

        return {"type": "suggest", "report": "Report unavailable"}
