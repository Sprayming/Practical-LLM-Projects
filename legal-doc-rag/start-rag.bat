@echo off
set PATH=%PATH%;C:\Program Files\Docker\Docker\resources\bin
echo Legal Document RAG - FastAPI
echo
docker info>nul 2>&1
if %errorlevel% neq 0 (
  echo Docker Desktop not running, starting...
  start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe"
  echo Waiting for Docker Engine...
  :wait_docker
  timeout /t 3 /nobreak >nul
  docker info>nul 2>&1
  if %errorlevel% neq 0 goto wait_docker
  echo Docker Engine ready!
)
echo
echo [1/3] Starting Redis...
docker start rag-redis 2>nul || docker run -d --name rag-redis -p 6379:6379 alpine:3.18 sh -c "apk add --no-cache redis && redis-server --bind 0.0.0.0"
echo [2/3] Starting App...
docker start rag-app 2>nul || docker run -d --name rag-app -p 8000:8000 --link rag-redis:redis -v rag-tenant-data:/app/tenant_data  -e REDIS_URL="redis://redis:6379/0" -e LLM_API_KEY="sk-d5f19a379ef944f1b5287c4ba8acd227" -e LLM_BASE_URL="https://api.deepseek.com/v1" -e EMBEDDING_API_KEY="df9c9b2d-35d9-4df6-b49d-f489708e1eab" -e EMBEDDING_BASE_URL="https://ark.cn-beijing.volces.com/api/v3" -e EMBEDDING_MODEL="ep-m-20251117205847-trwgz" -e EMBEDDER_TYPE="openai" legal-doc-rag-fastapi:latest
echo
echo App: http://localhost:8000
start http://localhost:8000
pause
