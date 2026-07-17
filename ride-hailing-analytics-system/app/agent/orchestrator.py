import sys, os, traceback
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.db.connection import execute_sql
from app.agent.planner import Plan, PlanStep, create_plan
from app.agent.tools.sql_tool import SQLTool
from app.agent.tools.analysis_tool import AnalysisTool
from app.agent.tools.report_tool import ReportTool


class Orchestrator:
    """Agent 调度器：执行计划中的每一步"""

    def __init__(self, api_key: str = "", base_url: str = ""):
        self.api_key = api_key
        self.base_url = base_url or os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1")
        self.sql_tool = SQLTool()
        self.analysis_tool = AnalysisTool(api_key, base_url)
        self.report_tool = ReportTool(api_key, base_url)

    def run(self, question: str) -> dict:
        plan = create_plan(question, self.api_key, self.base_url)
        results = {}
        errors = []

        for step in plan.steps:
            try:
                # Check dependencies
                for dep in step.depends_on:
                    if dep not in results:
                        raise ValueError(f"Dependency {dep} not satisfied")

                context = {k: v for k, v in results.items() if k in step.depends_on}

                if step.agent_type == "data":
                    result = self.sql_tool.execute(step, question)
                elif step.agent_type == "analysis":
                    result = self.analysis_tool.analyze(step, question, context, results)
                elif step.agent_type == "suggest":
                    result = self.report_tool.generate(step, question, results)
                else:
                    result = {"raw": f"Unknown agent type: {step.agent_type}"}

                results[step.step_id] = result

            except Exception as e:
                errors.append({"step": step.step_id, "error": str(e)})
                results[step.step_id] = {"error": str(e)}

        return {
            "question": question,
            "plan": [s.model_dump() for s in plan.steps],
            "results": {k: v for k, v in results.items()},
            "errors": errors,
            "final_report": self._build_report(results, plan),
        }

    def _build_report(self, results: dict, plan: Plan) -> str:
        data_results = [r for sid, r in results.items() if r.get("type") == "data" or sid == "01"]
        analysis_results = [r for sid, r in results.items() if r.get("type") == "analysis" or sid == "02"]
        report_results = [r for sid, r in results.items() if r.get("type") == "suggest" or sid == "03"]

        lines = ["## Analysis Report\\n"]

        for dr in data_results:
            if "summary" in dr:
                lines.append(f"### Data\\n{dr['summary']}\\n")

        for ar in analysis_results:
            if "analysis" in ar:
                lines.append(f"### Analysis\\n{ar['analysis']}\\n")

        for rr in report_results:
            if "report" in rr:
                lines.append(f"### Recommendation\\n{rr['report']}\\n")

        return "\\n".join(lines) if len(lines) > 2 else "No results available."
