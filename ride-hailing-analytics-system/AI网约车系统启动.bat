@echo off
REM ============================================================
REM ride-hailing-analytics-system - quick start (Windows)
REM Double-click to launch the FastAPI dev server on port 8001
REM ============================================================
cd /d %~dp0

REM Use the known conda interpreter; fall back to PATH python
set "PY=C:\Users\Lenovo\miniconda3\python.exe"
if not exist "%PY%" set "PY=python"

REM Generate sample data only when the database is missing
if not exist "data\ride_hailing.db" (
    echo [INFO] No database found. Generating sample data, please wait...
    "%PY%" scripts\generate_data.py
)

echo [INFO] Starting server at http://127.0.0.1:8001  (Ctrl+C to stop)
echo [INFO] Web UI : http://127.0.0.1:8001/
echo [INFO] API doc: http://127.0.0.1:8001/apiview   (offline)  or  /docs
echo [INFO] Opening the web UI in your default browser shortly...
echo.
REM Auto-open the web UI in the default browser after a short delay (so the server is up first)
start "" cmd /c "ping -n 8 127.0.0.1 >nul & start http://127.0.0.1:8001/"
"%PY%" -m uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload
