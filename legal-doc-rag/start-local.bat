@echo off
title Legal Document RAG (FastAPI Local)
echo ========================================
echo   Starting Legal Document RAG (Local)
echo ========================================
echo.

cd /d "D:\git\legal-doc-rag"

echo [1/2] Installing/updating dependencies...
pip install -r requirements-docker.txt >nul 2>&1

echo [2/2] Starting FastAPI backend...
echo   Open: http://localhost:8501
echo.
uvicorn app.main:app --host 127.0.0.1 --port 8501

pause