import os
from pathlib import Path

os.chdir("D:/git/legal-doc-rag")

# 从 .env 读取 Key（无 BOM）
env_path = Path(".env")
for line in open(env_path, "r", encoding="utf-8"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
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
