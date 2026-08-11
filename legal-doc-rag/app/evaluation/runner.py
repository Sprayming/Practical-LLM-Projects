"""
回归测试 Runner - 加载 Golden Test Set + RAGAS 评估 + 历史追踪

主要功能：
1. 加载预置的黄金测试集（golden test set）
2. 执行端到端的 RAGAS 评估
3. 追踪并记录评估指标的历史变化
4. 支持抽样测试以加快评估速度
"""
import json, os
from pathlib import Path
from datetime import datetime
from loguru import logger


def load_test_set(path=None):
    """
    加载预置的测试数据集。
    
    默认从项目 tests 目录下的 golden_test_set.json 文件加载测试问题集。
    该 JSON 文件应包含一个 questions 列表，每个元素是包含 question 和 ground_truth 的字典。
    
    Args:
        path (str, optional): 测试集文件的路径。如果未提供，使用默认路径。
        
    Returns:
        list: 包含测试问题的列表，每个元素是包含问题和标准答案的字典。
    """
    if path is None:
        # 默认路径：项目根目录/tests/golden_test_set.json
        path = str(Path(__file__).resolve().parent.parent.parent / "tests" / "golden_test_set.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)["questions"]


def run_regression(retriever_func, llm_func, sample_size=None):
    """
    执行完整的 RAG 回归测试流程。
    
    主要步骤：
    1. 加载测试问题集（可抽样）
    2. 对每个问题：
       - 使用提供的检索器获取相关文档
       - 使用提供的 LLM 生成答案
       - 构建评估样本
    3. 使用 RAGAS 框架进行评估
    4. 保存结果并计算与上一次测试的指标变化
    
    Args:
        retriever_func (callable): 接收问题字符串，返回相关文档列表的检索函数。
        llm_func (callable): 接收问题和上下文，返回答案的生成函数。
        sample_size (int, optional): 限制测试的问题数量，用于快速测试。
        
    Returns:
        dict: 包含当前评估结果和历史变化（delta）的字典。
    """
    # 1. 加载测试问题集
    questions = load_test_set()
    if sample_size:
        questions = questions[:sample_size]  # 支持抽样测试
    logger.info("Running regression: {} questions", len(questions))

    # 2. 处理依赖问题（临时模拟 vertexai 模块）
    import sys, types
    fake = types.ModuleType("langchain_community.chat_models.vertexai")
    class F: pass
    fake.ChatVertexAI = F
    sys.modules["langchain_community.chat_models.vertexai"] = fake

    # 3. 导入 RAGAS 评估组件
    from ragas.dataset_schema import SingleTurnSample, EvaluationDataset
    from ragas.metrics.collections import faithfulness, answer_relevancy, context_recall
    from ragas import evaluate

    # 4. 准备评估样本
    samples = []
    for i, q in enumerate(questions):
        logger.info("[{}/{}] {}", i+1, len(questions), q["question"][:40])  # 只显示问题前40字符
        
        # 执行检索
        docs = retriever_func(q["question"]) or []
        # 统一处理文档对象（兼容不同类型的检索器返回结果）
        contexts = [d.page_content[:500] for d in docs[:5]] if hasattr(docs[0], 'page_content') else [str(d)[:500] for d in docs[:5]]
        
        # 生成答案
        answer = llm_func(q["question"], contexts)
        
        # 构建评估样本
        samples.append(SingleTurnSample(
            question=q["question"],
            answer=answer,
            contexts=contexts,
            ground_truth=q["ground_truth"]
        ))

    # 5. 执行 RAGAS 评估
    logger.info("Evaluating with RAGAS...")
    dataset = EvaluationDataset.from_list(samples)
    result = evaluate(dataset, metrics=[faithfulness, answer_relevancy, context_recall])

    # 6. 处理评估结果
    metrics = {k: float(result.get(k, 0)) for k in ["faithfulness", "answer_relevancy", "context_recall"]}
    _save_history(metrics, len(questions))  # 保存历史记录
    
    # 7. 计算与上一次测试的指标变化
    prev = _get_previous()
    if prev:
        metrics["delta"] = {k: round(metrics[k] - prev[k], 4) for k in metrics}
    return metrics


def _save_history(metrics, count):
    """
    保存本次评估结果到历史记录文件中。
    
    每次测试都会在 regression_history.json 中追加一条记录，包含：
    - 时间戳
    - 测试样本数量
    - 各项评估指标
    
    Args:
        metrics (dict): 本次评估的各项指标。
        count (int): 本次测试使用的样本数量。
    """
    path = Path(__file__).resolve().parent.parent.parent / "tests" / "regression_history.json"
    # 如果历史文件存在则读取，否则初始化空列表
    history = json.loads(open(path).read()) if path.exists() else []
    # 追加新记录
    history.append({
        "timestamp": datetime.now().isoformat(),  # ISO 格式时间戳
        "sample_count": count,
        "metrics": metrics
    })
    # 保存回文件
    with open(path, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def _get_previous():
    """
    获取上一次测试的评估结果。
    
    从 regression_history.json 中读取倒数第二条记录（最新的是当前测试）。
    
    Returns:
        dict or None: 上一次测试的指标字典，如果没有历史记录则返回 None。
    """
    path = Path(__file__).resolve().parent.parent.parent / "tests" / "regression_history.json"
    if path.exists():
        history = json.loads(open(path).read())
        # 返回倒数第二条记录（最新的一条是当前测试）
        if len(history) >= 2: 
            return history[-2]["metrics"]
    return None
