@echo off
echo Starting Legal Document RAG...
docker info >nul 2>&1
if %errorlevel% neq 0 (
    echo Starting Docker Desktop...
    start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    :wait_docker
    timeout /t 3 >nul
    docker info >nul 2>&1
    if %errorlevel% neq 0 goto wait_docker
)
cd /d "D:\git\legal-doc-rag"

REM Check if Redis is already running
docker inspect rag-redis >nul 2>&1
if %errorlevel% neq 0 (
    echo Starting Redis manually...
    docker run -d --name rag-redis -p 6379:6379 redis:7-alpine >nul
)

echo Starting web app...
docker compose up -d app --no-deps >nul

REM Connect Redis to compose network
docker network connect --alias redis legal-doc-rag_default rag-redis >nul 2>&1

REM Restart app to connect to Redis
docker compose restart app >nul

timeout /t 5 >nul
start http://localhost:8501
echo Project started at http://localhost:8501
echo.
pause
