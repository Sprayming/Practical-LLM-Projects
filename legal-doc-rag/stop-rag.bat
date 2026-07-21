@echo off
cd /d "D:\git\legal-doc-rag"
echo ========================================
echo   Legal Document RAG - 一键停止
echo ========================================
echo.
echo 正在停止服务...
docker compose down
if %errorlevel% equ 0 (
    echo [OK] 服务已停止
) else (
    echo [ERROR] 停止失败
)
echo.
pause