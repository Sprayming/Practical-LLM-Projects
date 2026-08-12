
"""evaluate.py —— RAG 问答质量评估的一键启动入口（运行 RAG 评估）。

【作用与功能】
本脚本是一个极薄的"启动器 / 引导脚本"，本身不含评估算法，职责只有三件事：
1. 把项目根目录加入 sys.path，让脚本可直接运行并 import 到 app 包；
2. 手工解析项目根目录的 .env 并写入 os.environ（不依赖 python-dotenv）；
3. 把项目自定义的 LLM_API_KEY / LLM_BASE_URL 映射成 OpenAI SDK 约定的
   OPENAI_API_KEY / OPENAI_BASE_URL —— 因为 RAGAS 及 langchain-openai 等
   评估侧依赖只认 OPENAI_* 这套标准变量名。
准备好环境后，调用 `app.evaluation.evaluator.run_evaluation()` 执行真正的评估，
结果保存在模块级变量 `result` 中。

【主要组成】
- 模块级流程（本文件无自定义函数）：
  - sys.path 注入：保证 `python scripts/evaluate.py` 直接运行时能找到 app 包
  - .env 手工解析：逐行读取 KEY=VALUE 写入环境变量
  - 环境变量映射：LLM_API_KEY → OPENAI_API_KEY，LLM_BASE_URL → OPENAI_BASE_URL
  - `run_evaluation()`：真正的评估逻辑，由 app.evaluation.evaluator 提供

【适用场景】
- 场景1：本地或 CI 中跑一次完整 RAG 评估 —— `python scripts/evaluate.py`
- 场景2：只想复用"环境变量准备 + 调用评估"这一最简链路，不需要 run_ragas_eval.py
  里那套自定义 embedding / 报告落盘逻辑时
- 注意：import 顺序刻意如此——环境变量必须在 import evaluator 之前写好，
  否则被 import 的模块在初始化时读不到 OPENAI_* 配置

【依赖关系】
- 内部模块：app.evaluation.evaluator.run_evaluation
- 环境变量：LLM_API_KEY、LLM_BASE_URL（由 .env 提供，映射为 OPENAI_*）
- 前置文件：项目根目录必须存在 `.env`，否则第 9 行 open() 会抛 FileNotFoundError
- 网络要求：评估过程需调用外部 LLM 接口，会产生 token 消耗
"""
import os, sys
# 把项目根目录（scripts/ 的上一级）插到 sys.path 首位，
# 使 `python scripts/evaluate.py` 这种直接运行方式也能 import 到 app 包
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pathlib import Path

# 加载 .env
# 这里手工解析而不用 python-dotenv：少一个依赖，且逻辑足够简单可控
env_path = Path(__file__).resolve().parent.parent / ".env"
for line in open(env_path, "r", encoding="utf-8"):
    line = line.strip()
    # 过滤空行、以 # 开头的注释行、以及不含 "=" 的非法行
    if line and not line.startswith("#") and "=" in line:
        # split("=", 1) 只按第一个等号切分，保证值里含 "="（如 URL、base64）不被截断
        k, v = line.split("=", 1)
        os.environ[k.strip()] = v.strip()

# 映射到 OPENAI 环境变量
# RAGAS / langchain-openai 等评估依赖只读取 OPENAI_* 标准变量名，
# 因此把项目自定义的 LLM_* 配置转写一份过去（仅在有值时覆盖）
if os.getenv("LLM_API_KEY"):
    os.environ["OPENAI_API_KEY"] = os.getenv("LLM_API_KEY")
if os.getenv("LLM_BASE_URL"):
    os.environ["OPENAI_BASE_URL"] = os.getenv("LLM_BASE_URL")

# 必须在环境变量全部就绪之后再 import：
# evaluator 模块在导入期就会读取 OPENAI_* 构建客户端，提前 import 会拿到空配置
from app.evaluation.evaluator import run_evaluation
# 执行评估；返回的指标结果保存在模块级变量 result 中（供交互式运行时查看）
result = run_evaluation()