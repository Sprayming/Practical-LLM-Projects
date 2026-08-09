@echo off
title 法律文书 RAG 系统
echo ========================================
echo   法律文书 RAG 系统 (FastAPI Local)
echo ========================================
echo.

cd /d "D:\git\legal-doc-rag"

echo [1/2] 正在启动后端 (http://localhost:8000) ...
start "" "C:\Users\11195\miniconda3\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000

echo [2/2] 等待服务就绪...
:wait_ready
timeout /t 2 /nobreak >nul
curl.exe -s http://localhost:8000/health >nul 2>&1
if %errorlevel% neq 0 goto wait_ready

echo.
echo ========================================
echo   启动完成！正在打开 http://localhost:8000
echo ========================================
start "" "http://localhost:8000"
exit /b 0
