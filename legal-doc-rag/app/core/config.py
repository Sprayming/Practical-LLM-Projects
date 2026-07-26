import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# LLM
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-v4-pro")

# Embedding
EMBEDDER_TYPE = os.getenv("EMBEDDER_TYPE", "openai")
EMBEDDING_API_KEY = os.getenv("EMBEDDING_API_KEY", "df9c9b2d-35d9-4df6-b49d-f489708e1eab")
EMBEDDING_BASE_URL = os.getenv("EMBEDDING_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "ep-m-20251117205847-trwgz")

# Storage
CHROMA_PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR", "./chroma_db")
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "./uploads")

# Redis
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# JWT
JWT_SECRET = os.getenv("JWT_SECRET", "legal-rag-secret-key-change-in-production")

# Paths
TENANT_DB = str(BASE_DIR / "tenant_data" / "users.db")
