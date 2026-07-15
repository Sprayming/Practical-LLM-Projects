"""回归测试入口 - python scripts/run_regression.py"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path
from dotenv import load_dotenv
env_path = Path(__file__).resolve().parent.parent / ".env"
if env_path.exists(): load_dotenv(str(env_path))

from app.evaluation.runner import run_regression, load_test_set

def dummy_retriever(query):
    """示例检索函数"""
    return []

def dummy_llm(query, contexts):
    """示例生成函数"""
    return "基于提供的资料，这是一个示例回答。"

if __name__ == "__main__":
    ts = load_test_set()
    print(f"Test set loaded: {len(ts)} questions")
    result = run_regression(dummy_retriever, dummy_llm, sample_size=3)
    print(f"Faithfulness: {result.get('faithfulness', 'N/A')}")
    print(f"AnswerRelevancy: {result.get('answer_relevancy', 'N/A')}")
    print(f"ContextRecall: {result.get('context_recall', 'N/A')}")