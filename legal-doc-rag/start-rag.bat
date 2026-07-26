@echo off
set PATH=%PATH%;C:\Program Files\Docker\Docker\resources\bin
echo Legal Document RAG - FastAPI
docker info>nul 2>&1
if %errorlevel% neq 0 (
  echo Docker Desktop not running.
  echo Use: python -m uvicorn app.main:app
  pause
  exit
)
echo Starting...
docker start legal-doc-rag-redis-1 2>nul || docker run -d --name legal-doc-rag-redis-1 -p 6379:6379 --restart unless-stopped alpine:3.18 sh -c "apk add --no-cache redis && redis-server --bind 0.0.0.0"
docker start legal-doc-rag-app-1 2>nul || docker run -d --name legal-doc-rag-app-1 -p 8000:8000 --link legal-doc-rag-redis-1:redis -e REDIS_URL=redis://redis:6379/0 -e LLM_API_KEY=sk-d5f19a379ef944f1b5287c4ba8acd227 -e LLM_BASE_URL=https://api.deepseek.com/v1 -e LLM_MODEL=deepseek-v4-pro -e EMBEDDING_API_KEY=df9c9b2d-35d9-4df6-b49d-f489708e1ab -e EMBEDDING_BASE_URL=https://ark.cn-beijing.volces.com/api/v3 -e EMBEDDING_MODEL=ep-m-20251117205847-trwgz -e EMBEDDER_TYPE=openai legal-doc-rag-fastapi:latest
start http://localhost:8000
pause
