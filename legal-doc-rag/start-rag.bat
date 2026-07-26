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
docker start rag-app 2>nul || docker run -d --name rag-app -p 8000:8000 --link rag-redis:redis legal-doc-rag-fastapi:latest
echo
echo App: http://localhost:8000
start http://localhost:8000
pause
