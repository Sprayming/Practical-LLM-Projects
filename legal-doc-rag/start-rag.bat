@echo off
echo Checking Docker...
docker info >nul 2>&1
if %errorlevel% neq 0 (
    echo Docker not running. Starting Docker Desktop...
    start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    echo Waiting for Docker to be ready...
    :wait
    timeout /t 3 /nobreak >nul
    docker info >nul 2>&1
    if %errorlevel% neq 0 goto wait
    echo Docker ready!
)

echo Starting RAG project...
cd /d D:\git\legal-doc-rag
docker compose up -d >nul
timeout /t 3 /nobreak >nul
start http://localhost:8501
echo Project started at http://localhost:8501
pause
