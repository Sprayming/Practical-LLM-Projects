@echo off
title Legal Document RAG - FastAPI
echo ========================================
echo   Legal Document RAG - FastAPI
echo ========================================
echo.

REM 1. Check/start Docker Desktop
echo [1/3] Checking Docker...
docker info >nul 2>&1
if %errorlevel% neq 0 (
    echo   Docker Desktop not running, starting...
    start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    :wait_docker
    timeout /t 3 /nobreak >nul
    docker info >nul 2>&1
    if %errorlevel% neq 0 goto wait_docker
)
echo   [OK] Docker is running

cd /d "D:\git\legal-doc-rag"

REM 2. Start stack with docker compose
echo [2/3] Starting services (Redis + App)...
docker compose up -d 2>&1
echo   [OK] Services started

REM 3. Wait for FastAPI to be ready
echo [3/3] Waiting for app to be ready...
:wait_ready
timeout /t 2 /nobreak >nul
curl.exe -s http://localhost:8000/api/health >nul 2>&1
if %errorlevel% neq 0 goto wait_ready

echo.
echo ========================================
echo   App is ready!
echo   Open: http://localhost:8000
echo ========================================
start http://localhost:8000
exit /b 0