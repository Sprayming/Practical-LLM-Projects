
"""运行 RAG 评估"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pathlib import Path

# 加载 .env
env_path = Path(__file__).resolve().parent.parent / ".env"
for line in open(env_path, "r", encoding="utf-8"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ[k.strip()] = v.strip()

# 映射到 OPENAI 环境变量
if os.getenv("LLM_API_KEY"):
    os.environ["OPENAI_API_KEY"] = os.getenv("LLM_API_KEY")
if os.getenv("LLM_BASE_URL"):
    os.environ["OPENAI_BASE_URL"] = os.getenv("LLM_BASE_URL")

from app.evaluation.evaluator import run_evaluation
result = run_evaluation()