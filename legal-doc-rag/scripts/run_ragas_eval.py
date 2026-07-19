import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ragas import evaluate
from ragas.dataset_schema import SingleTurnSample, EvaluationDataset
from ragas.metrics.collections import faithfulness, answer_relevancy, context_precision, context_recall

TEST_QUESTIONS = [
  {
    "question": "建立劳动关系需要签订什么形式的合同？",
    "ground_truth": "应当订立书面劳动合同"
  },
  {
    "question": "已建立劳动关系但未同时订立书面合同的，应在多久内补签？",
    "ground_truth": "自用工之日起一个月内"
  },
  {
    "question": "什么是无固定期限劳动合同？",
    "ground_truth": "用人单位与劳动者约定无确定终止时间的劳动合同"
  },
  {
    "question": "劳动者在同一单位连续工作满多少年可以要求订立无固定期限合同？",
    "ground_truth": "连续工作满十年"
  },
  {
    "question": "连续订立两次固定期限劳动合同后续签有什么规定？",
    "ground_truth": "应当订立无固定期限劳动合同"
  },
  {
    "question": "经济补偿按什么标准计算？",
    "ground_truth": "每满一年支付一个月工资"
  }
]

def run_evaluation(data_path=None):
    """Run RAGAS evaluation on the golden test set."""
    samples = []
    for i, item in enumerate(TEST_QUESTIONS, 1):
        q = item["question"]
        contexts = item.get("contexts", [])
        answer = contexts[0] if contexts else "No relevant context found."
        ground_truth = item.get("ground_truth", "")
        samples.append(SingleTurnSample(question=q, answer=answer, contexts=contexts, ground_truth=ground_truth))

    print("Running RAGAS evaluation...")
    dataset = EvaluationDataset.from_list(samples)
    result = evaluate(dataset, metrics=[faithfulness, answer_relevancy, context_precision, context_recall])

    print("\n=== Evaluation Report ===")
    labels = {"faithfulness": "Faithfulness", "answer_relevancy": "Answer Relevancy", "context_precision": "Context Precision", "context_recall": "Context Recall"}
    for key, label in labels.items():
        val = result.get(key, 0)
        print(f"  {label}: {float(val):.4f}" if isinstance(val, (int, float)) else f"  {label}: {val}")

    report_path = os.path.join(os.path.dirname(__file__), "..", "evaluation_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        metrics = {k: float(result[k]) if isinstance(result.get(k), (int, float)) else str(result.get(k, 0)) for k in labels}
        json.dump({"metrics": metrics}, f, ensure_ascii=False, indent=2)
    print(f"\nReport saved: {report_path}")
    return result

if __name__ == "__main__":
    run_evaluation()