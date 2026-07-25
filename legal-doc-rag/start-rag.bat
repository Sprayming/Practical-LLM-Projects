@echo off
set PATH=%PATH%;C:\Program Files\Docker\Docker\resources\bin

echo Checking Docker...
docker info >nul 2>&1
if %errorlevel% neq 0 (
    echo Docker Desktop is not running. Starting it...
    start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    echo Waiting for Docker Engine...
    :wait
    timeout /t 3 /nobreak >nul
    docker info >nul 2>&1
    if %errorlevel% neq 0 goto wait
    echo Docker Engine ready!
)

echo Starting RAG containers...

REM 启动 Redis
docker start legal-doc-rag-redis-1 >nul 2>&1 || docker run -d --name legal-doc-rag-redis-1 -p 6379:6379 --restart unless-stopped alpine:3.18 sh -c "apk add --no-cache redis && redis-server --bind 0.0.0.0"

REM 启动 App（传递 Embedding 和 LLM 配置）
docker start legal-doc-rag-app-1 >nul 2>&1 || docker run -d --name legal-doc-rag-app-1 -p 8501:8501 --restart unless-stopped ^
  --link legal-doc-rag-redis-1:redis ^
  -e REDIS_URL="redis://redis:6379/0" ^
  -e LLM_API_KEY="sk-d5f19a379ef944f1b5287c4ba8acd227" ^
  -e LLM_BASE_URL="https://api.deepseek.com/v1" ^
  -e EMBEDDING_API_KEY="df9c9b2d-35d9-4df6-b49d-f489708e1eab" ^
  -e EMBEDDING_BASE_URL="https://ark.cn-beijing.volces.com/api/v3" ^
  -e EMBEDDING_MODEL="ep-m-20251117205847-trwgz" ^
  -e EMBEDDER_TYPE="openai" ^
  legal-doc-rag_app:latest

echo Opening http://localhost:8501 ...
start http://localhost:8501
echo Done! Press any key to exit.
pause