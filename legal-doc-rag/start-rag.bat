@echo off
cd /d D:\git\legal-doc-rag
docker compose up -d
timeout /t 3 /nobreak >nul
start http://localhost:8501
echo Start completed, browser opened
pause
