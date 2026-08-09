@echo off
title 法律文书 RAG 系统
cd /d "D:\git\legal-doc-rag"
set "LOG=%~dp0start-rag.log"
set "PORT=8000"
echo [%date% %time%] === 启动脚本开始 === > "%LOG%"

netstat -ano 2>nul | findstr /r ":%PORT% " >nul
if %errorlevel% == 0 (
    echo [错误] 端口 %PORT% 已被占用，请先关闭占用程序后重试。 >> "%LOG%"
    echo [错误] 端口 %PORT% 已被占用!请先关闭占用程序后重试。
    pause
    exit /b 1
)

echo [1/2] 正在启动后端 (http://localhost:%PORT%) ...
echo 启动命令: C:\Users\11195\miniconda3\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port %PORT% >> "%LOG%"
start "uvicorn" cmd /c "C:\Users\11195\miniconda3\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 & echo uvicorn 已退出，按任意键关闭 & pause"

echo [2/2] 等待服务就绪，最多 60 秒...
set tries=0
:wait
timeout /t 2 /nobreak >nul
curl.exe -s -o nul http://localhost:%PORT%/ >nul 2>&1
if %errorlevel% == 0 goto ok
set /a tries+=1
if %tries% geq 30 (
    echo [错误] 启动超时，请查看弹出的 uvicorn 窗口或 start-rag.log。 >> "%LOG%"
    echo [错误] 启动超时!请查看 uvicorn 窗口报错或 start-rag.log。
    pause
    exit /b 1
)
goto wait

:ok
echo.
echo ========================================
echo   启动完成!正在打开 http://localhost:%PORT%
echo ========================================
start "" "http://localhost:%PORT%"
exit /b 0
