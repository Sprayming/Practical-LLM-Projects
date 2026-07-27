@echo off
title Legal Document RAG
echo ========================================
echo   Starting Legal Document RAG
echo ========================================
echo.

REM 1. Check Docker
echo [1/4] Checking Docker...
docker info >nul 2>&1
if %errorlevel% neq 0 (
    echo   Docker not running. Starting Docker Desktop...
    start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    :wait_docker
    timeout /t 3 /nobreak >nul
    docker info >nul 2>&1
    if %errorlevel% neq 0 goto wait_docker
)
echo   [OK] Docker is running

cd /d "D:\git\legal-doc-rag"

REM 2. Start Redis
echo [2/4] Starting Redis...
docker inspect rag-redis >nul 2>&1
if %errorlevel% neq 0 (
    docker run -d --name rag-redis -p 6379:6379 redis:7-alpine >nul
)
echo   [OK] Redis is running

REM 3. Start web app
echo [3/4] Starting web app...
docker compose up -d app --no-deps >nul 2>&1
docker network connect --alias redis legal-doc-rag_default rag-redis >nul 2>&1
docker compose restart app >nul 2>&1
echo   [OK] App is running

REM 4. Wait for app to be ready, then open browser
echo [4/4] Waiting for app to be ready...
:wait_ready
timeout /t 2 /nobreak >nul
curl -s http://localhost:8501 >nul 2>&1
if %errorlevel% neq 0 goto wait_ready

echo.
echo ========================================
echo   App is ready!
echo   Open: http://localhost:8501
echo   Password: rag2024
echo ========================================
start http://localhost:8501
pause
