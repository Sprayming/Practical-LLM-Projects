"""run_regression.py —— RAG 质量回归测试入口（回归测试入口 - python scripts/run_regression.py）。

【作用与功能】
本脚本是"评测回归"的命令行入口 / 冒烟骨架。它演示并驱动
`app.evaluation.runner` 提供的回归框架：
1. 加载项目内置的回归测试集（问题 + 参考答案）；
2. 传入一对"检索函数"和"生成函数"（本文件给的是占位实现）；
3. 由 runner 抽样若干条样本跑完整评测，输出忠实度 / 答案相关性 / 上下文召回三项指标。

重要说明：文件中的 `dummy_retriever` / `dummy_llm` 是**占位（示例）实现**——
一个返回空上下文、一个返回固定文案。因此直接运行本脚本得到的指标是基线参照，
不代表真实系统质量。实际回归时应把这两个参数替换为项目真实的
混合检索器与 LLM 生成函数（保持同样的函数签名即可无缝替换）。

【主要组成】
- `dummy_retriever`：示例检索函数，签名 `(query) -> list`，恒返回空列表
- `dummy_llm`：示例生成函数，签名 `(query, contexts) -> str`，恒返回固定示例回答
- `__main__` 主流程：加载测试集 → 抽样 3 条跑回归 → 打印三项核心指标

【适用场景】
- 场景1：验证评测框架本身是否接线正常（冒烟测试）——
  `python scripts/run_regression.py`
- 场景2：作为模板，把 dummy 函数替换成真实检索/生成实现后跑质量回归
- 场景3：CI 中作为轻量守护，确认 `load_test_set` / `run_regression` 接口未被改坏

【依赖关系】
- 内部模块：`app.evaluation.runner`（提供 `run_regression`、`load_test_set`）
- 第三方库：python-dotenv
- 环境变量：由项目根目录 `.env` 提供（.env 不存在时静默跳过，使用系统环境变量）
- 前置要求：`sample_size=3` 意味着测试集至少要有样本，否则 runner 可能返回空指标
"""
import sys, os
# 把项目根目录插入 sys.path 首位，保证脚本直接运行时能 import 到 app 包
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path
from dotenv import load_dotenv
# 加载 .env（API 密钥、模型地址等）；文件不存在则跳过，不阻断执行
env_path = Path(__file__).resolve().parent.parent / ".env"
if env_path.exists(): load_dotenv(str(env_path))

# 必须在 sys.path 与环境变量准备完毕后再导入项目内模块
from app.evaluation.runner import run_regression, load_test_set

def dummy_retriever(query):
    """示例检索函数（占位实现），恒返回空上下文列表。

    参数:
        query (str): 用户查询文本
    返回:
        list: 检索到的上下文片段列表；此占位实现始终返回空列表 []
    适用场景:
        - 验证回归框架能否在"完全检索不到内容"的极端情况下正常跑完
        - 作为接口模板：真实检索器只需保持 `(query) -> list` 这一签名即可替换本函数
    """
    return []

def dummy_llm(query, contexts):
    """示例生成函数（占位实现），恒返回一句固定的示例回答。

    参数:
        query (str): 用户查询文本
        contexts (list): 由检索函数产出的上下文片段列表
    返回:
        str: 生成的答案文本；此占位实现始终返回同一句示例回答
    适用场景:
        - 不消耗任何 token 地跑通评测链路，确认框架接线正确
        - 作为接口模板：真实生成函数只需保持 `(query, contexts) -> str` 签名即可替换
    """
    return "基于提供的资料，这是一个示例回答。"

if __name__ == "__main__":
    # 步骤1：加载回归测试集，并打印题量以确认数据文件被正确读取
    ts = load_test_set()
    print(f"Test set loaded: {len(ts)} questions")
    # 步骤2：抽样 3 条跑回归（sample_size 控制样本数，值越小越省时间与 token）
    result = run_regression(dummy_retriever, dummy_llm, sample_size=3)
    # 步骤3：打印三项核心指标；用 .get(..., 'N/A') 兜底，
    # 避免某项指标未计算成功时抛 KeyError 中断输出
    print(f"Faithfulness: {result.get('faithfulness', 'N/A')}")        # 忠实度：是否基于上下文作答
    print(f"AnswerRelevancy: {result.get('answer_relevancy', 'N/A')}")  # 答案相关性：是否切题
    print(f"ContextRecall: {result.get('context_recall', 'N/A')}")      # 上下文召回：相关内容是否找全