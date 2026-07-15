# =+= NEW MODULE - Added 2026-07-15 by Codex =+=\n\n"""运行回归测试"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from loguru import logger
logger.remove()

from app.evaluation.runner import run_regression, print_report
from app.evaluation.metrics import load_test_set

# 简单的检索和生成函数（测试用）
def dummy_retriever(query):
    from app.retrieval.vector_store import get_vector_store
    store = get_vector_store()
    # 需要从store获取数据
    logger.info("Dummy retriever: {}", query)
    return []

def dummy_llm(query, contexts):
    return "基于提供的资料，这是一个示例回答。"

if __name__ == "__main__":
    ts = load_test_set()
    print(f"Test set loaded: {len(ts)} questions")
    report = run_regression(dummy_retriever, dummy_llm, sample_size=3)
    print_report(report)