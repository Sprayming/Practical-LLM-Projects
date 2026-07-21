@echo off
cd /d "D:\git\legal-doc-rag"
echo ========================================
echo   Legal Document RAG - 一键启动
echo ========================================
echo.
echo [1/3] 检测 Docker 运行状态...
docker info >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Docker 未运行！请先启动 Docker Desktop
    echo.
    pause
    exit /b 1
)
echo [OK] Docker 运行中
echo.
echo [2/3] 启动服务...
docker compose up -d
if %errorlevel% neq 0 (
    echo [ERROR] 启动失败
    pause
    exit /b 1
)
echo [OK] 服务已启动
echo.
echo [3/3] 等待服务就绪...
timeout /t 3 /nobreak >nul
start http://localhost:8501
echo.
echo ========================================
echo   访问地址: http://localhost:8501
echo   关闭服务: 双击 stop-rag.bat
echo ========================================
echo.
pause