@echo off
title 法律文书 RAG 系统
cd /d "D:\git\legal-doc-rag"

set "LOG=%~dp0start-rag.log"
set "PORT=8000"
echo [%date% %time%] === 启动脚本开始 === > "%LOG%"

REM 端口预检: 检测 8000 是否被占用
netstat -ano 2>nul | findstr ":8000" >nul
if %errorlevel% == 0 (
    echo [错误] 端口 8000 已被占用,请先关闭占用它的程序,例如旧服务、Docker 或其他,然后重试。 >> "%LOG%"
    echo [错误] 端口 8000 已被占用!请先关闭占用程序后重试。
    pause
    exit /b 1
)

echo [1/2] 正在启动后端 (http://localhost:8000) ...
echo [%date% %time%] 启动命令: C:\Users\11195\miniconda3\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 >> "%LOG%"
start "" "C:\Users\11195\miniconda3\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000

echo [2/2] 等待服务就绪,最多 60 秒...
set tries=0
:wait
timeout /t 2 /nobreak >nul
curl.exe -s http://localhost:8000/health >nul 2>&1
if %errorlevel% == 0 goto ok
set /a tries+=1
if %tries% geq 30 (
    echo [错误] 启动超时,服务未在 60 秒内就绪。请查看 start-rag.log 或弹出的 uvicorn 窗口报错。 >> "%LOG%"
    echo [错误] 启动超时!请查看日志或 uvicorn 窗口报错。
    pause
    exit /b 1
)
goto wait

:ok
echo.
echo ========================================
echo   启动完成!正在打开 http://localhost:8000
echo ========================================
start "" "http://localhost:8000"
exit /b 0
