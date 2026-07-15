# =+= NEW MODULE - Added 2026-07-15 by Codex =+=\n\n"""
RAGAS 评估 - Faithfulness / AnswerRelevancy / ContextRecall 三维度打分
"""
import json, os, sys, types
from pathlib import Path
from loguru import logger

# 修复 vertexai 依赖问题
fake = types.ModuleType("langchain_community.chat_models.vertexai")
class Fake: pass
fake.ChatVertexAI = Fake
sys.modules["langchain_community.chat_models.vertexai"] = fake

from ragas.dataset_schema import SingleTurnSample, EvaluationDataset
from ragas.metrics.collections import faithfulness, answer_relevancy, context_recall
from ragas import evaluate


def load_test_set(path: str = None) -> list[dict]:
    """加载 Golden Test Set"""
    if path is None:
        path = str(Path(__file__).resolve().parent.parent.parent / "tests" / "golden_test_set.json")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data["questions"]


def run_evaluation(
    questions: list[dict],
    retriever_func,
    llm_func,
    sample_size: int = None,
) -> dict:
    """运行 RAGAS 评估"""
    if sample_size:
        questions = questions[:sample_size]

    samples = []
    for i, q in enumerate(questions):
        logger.info("Evaluating [{}/{}]: {}", i + 1, len(questions), q["question"][:40])

        # 检索
        docs = retriever_func(q["question"])
        contexts = [d.content if hasattr(d, "content") else d.page_content for d in docs[:5]]

        # 生成
        answer = llm_func(q["question"], contexts)

        samples.append(SingleTurnSample(
            question=q["question"],
            answer=answer,
            contexts=contexts,
            ground_truth=q["ground_truth"],
        ))

    logger.info("Running RAGAS evaluation on {} samples...", len(samples))
    dataset = EvaluationDataset.from_list(samples)
    result = evaluate(dataset, metrics=[faithfulness, answer_relevancy, context_recall])

    metrics = {
        "faithfulness": float(result.get("faithfulness", 0)),
        "answer_relevancy": float(result.get("answer_relevancy", 0)),
        "context_recall": float(result.get("context_recall", 0)),
    }
    return metrics