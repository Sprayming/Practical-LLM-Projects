"""回归测试 Runner - 加载 Golden Test Set + RAGAS 评估 + 历史追踪"""
import json, os
from pathlib import Path
from datetime import datetime
from loguru import logger

def load_test_set(path=None):
    if path is None:
        path = str(Path(__file__).resolve().parent.parent.parent / "tests" / "golden_test_set.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)["questions"]

def run_regression(retriever_func, llm_func, sample_size=None):
    """执行回归测试"""
    questions = load_test_set()
    if sample_size:
        questions = questions[:sample_size]
    logger.info("Running regression: {} questions", len(questions))

    import sys, types
    fake = types.ModuleType("langchain_community.chat_models.vertexai")
    class F: pass
    fake.ChatVertexAI = F
    sys.modules["langchain_community.chat_models.vertexai"] = fake

    from ragas.dataset_schema import SingleTurnSample, EvaluationDataset
    from ragas.metrics.collections import faithfulness, answer_relevancy, context_recall
    from ragas import evaluate

    samples = []
    for i, q in enumerate(questions):
        logger.info("[{}/{}] {}", i+1, len(questions), q["question"][:40])
        docs = retriever_func(q["question"]) or []
        contexts = [d.page_content[:500] for d in docs[:5]] if hasattr(docs[0], 'page_content') else [str(d)[:500] for d in docs[:5]]
        answer = llm_func(q["question"], contexts)
        samples.append(SingleTurnSample(question=q["question"], answer=answer, contexts=contexts, ground_truth=q["ground_truth"]))

    logger.info("Evaluating with RAGAS...")
    dataset = EvaluationDataset.from_list(samples)
    result = evaluate(dataset, metrics=[faithfulness, answer_relevancy, context_recall])

    metrics = {k: float(result.get(k, 0)) for k in ["faithfulness", "answer_relevancy", "context_recall"]}
    _save_history(metrics, len(questions))
    prev = _get_previous()
    if prev:
        metrics["delta"] = {k: round(metrics[k] - prev[k], 4) for k in metrics}
    return metrics

def _save_history(metrics, count):
    path = Path(__file__).resolve().parent.parent.parent / "tests" / "regression_history.json"
    history = json.loads(open(path).read()) if path.exists() else []
    history.append({"timestamp": datetime.now().isoformat(), "sample_count": count, "metrics": metrics})
    with open(path, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

def _get_previous():
    path = Path(__file__).resolve().parent.parent.parent / "tests" / "regression_history.json"
    if path.exists():
        h = json.loads(open(path).read())
        if len(h) >= 2: return h[-2]["metrics"]
    return None