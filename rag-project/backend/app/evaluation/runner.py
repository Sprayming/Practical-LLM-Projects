# =+= NEW MODULE - Added 2026-07-15 by Codex =+=\n\n"""
回归测试 - 全量 Golden Test Set 评估 + 指标追踪
"""
import json, os
from pathlib import Path
from datetime import datetime
from loguru import logger
from app.evaluation.metrics import load_test_set, run_evaluation


def run_regression(retriever_func, llm_func, sample_size: int = None) -> dict:
    """执行全量回归测试"""
    questions = load_test_set()
    if sample_size:
        questions = questions[:sample_size]
        logger.info("Running regression: {} samples (subset)", len(questions))
    else:
        logger.info("Running regression: {} samples (full)", len(questions))

    result = run_evaluation(questions, retriever_func, llm_func)

    # 记录历史
    history_path = Path(__file__).resolve().parent.parent.parent / "tests" / "regression_history.json"
    history = []
    if history_path.exists():
        with open(history_path, "r") as f:
            history = json.load(f)

    entry = {
        "timestamp": datetime.now().isoformat(),
        "sample_count": len(questions),
        "metrics": result,
    }
    history.append(entry)

    with open(history_path, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

    # 对比上次
    report = {"current": result, "history": history}
    if len(history) >= 2:
        prev = history[-2]["metrics"]
        deltas = {k: round(result[k] - prev[k], 4) for k in result}
        report["delta_vs_previous"] = deltas
        logger.info("Faithfulness: {:.4f} (Δ{:.4f})", result["faithfulness"], deltas["faithfulness"])

    return report


def print_report(report: dict):
    """打印评估报告"""
    print("\n" + "=" * 50)
    print("回归测试报告")
    print("=" * 50)
    print(f"样本数: {len(report.get('history', []))}")
    for key, label in [("faithfulness", "忠实度"), ("answer_relevancy", "相关性"), ("context_recall", "召回率")]:
        val = report["current"].get(key, 0)
        delta = report.get("delta_vs_previous", {}).get(key, 0)
        delta_str = f" (Δ{delta:+.4f})" if delta else ""
        print(f"  {label}: {val:.4f}{delta_str}")
    print("=" * 50)