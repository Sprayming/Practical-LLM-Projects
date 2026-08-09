@echo off
setlocal
set DIR=D:\git\legal-doc-rag
set PORT=8000
set PY=%DIR%\.ocr_venv\Scripts\python.exe
title Legal-DOC-RAG Server (port 8000)

cd /d "%DIR%"

echo Starting Legal-DOC-RAG on port %PORT% ...
echo Python: %PY%

REM --- free port 8000 if something else is holding it ---
for /f "tokens=5" %%a in ('netstat -ano ^| findstr /i ":%PORT% "') do (
    echo Port %PORT% is occupied by PID %%a, stopping it ...
    taskkill /f /pid %%a >nul 2>&1
)
timeout /t 2 >nul

REM --- launch uvicorn in its own window (stays open for logs/errors) ---
echo Launching uvicorn (keep this window open while using the system) ...
start "Legal-DOC-RAG uvicorn" cmd /k ""%PY%" -m uvicorn app.main:app --host 127.0.0.1 --port %PORT%"

REM --- wait until the server answers on the root path ---
for /L %%i in (1,1,40) do (
    curl.exe -s -o nul http://localhost:%PORT%/
    if not errorlevel 1 goto OPEN
    timeout /t 2 >nul
)

echo ERROR: server did not respond within 80 seconds.
echo Check the uvicorn window for errors.
pause
exit /b 1

:OPEN
echo Server is up. Opening browser ...
start http://localhost:%PORT%/
echo Done.
