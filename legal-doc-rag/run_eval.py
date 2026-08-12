"""
run_eval.py —— RAG 系统评估运行入口

【作用与功能】
切换工作目录到项目根，从 .env 手动解析 LLM 相关配置（规避 BOM 编码问题），
并将其映射为 RAGAS 所需的标准 OPENAI 环境变量，最后调用评估器执行评测。

【主要组成】
- 顶层逻辑：chdir 到项目根目录 → 解析 .env → 映射 OPENAI 环境变量 → 运行 `run_evaluation()`。

【适用场景】
- 场景1：本地执行 `python run_eval.py` 跑 RAGAS 评估
- 场景2：在已配置 LLM_API_KEY / LLM_BASE_URL 的环境中复现评测

【依赖关系】
- 依赖项目根目录下的 `.env`（含 LLM_API_KEY、LLM_BASE_URL）
- 依赖 `app.evaluation.evaluator.run_evaluation` 评估实现
- 需存在可访问的 LLM 网关（与 LLM_BASE_URL 对应）
"""
import os
from pathlib import Path

# 切换到项目根目录，保证后续相对路径（.env、模型缓存等）解析正确
os.chdir("D:/git/legal-doc-rag")

# 从 .env 读取 Key（无 BOM）
env_path = Path(".env")
for line in open(env_path, "r", encoding="utf-8"):
    line = line.strip()
    # 跳过空行与注释行（# 开头），仅处理形如 KEY=VALUE 的配置行
    if line and not line.startswith("#") and "=" in line:
        # 按首个等号切分，左为键、右为值，去除两侧空白后写入环境变量
        k, v = line.split("=", 1)
        os.environ[k.strip()] = v.strip()

# 映射到 OPENAI 环境变量（RAGAS 用）
if os.getenv("LLM_API_KEY"):
    os.environ["OPENAI_API_KEY"] = os.getenv("LLM_API_KEY")
if os.getenv("LLM_BASE_URL"):
    os.environ["OPENAI_BASE_URL"] = os.getenv("LLM_BASE_URL")

print("API Key:", bool(os.environ.get("OPENAI_API_KEY")))

# 运行评估
from app.evaluation.evaluator import run_evaluation
result = run_evaluation()
