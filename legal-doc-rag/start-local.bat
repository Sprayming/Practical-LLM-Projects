@echo off
cd /d D:\git\legal-doc-rag
set STREAMLIT_EMAIL=
set STREAMLIT_SERVER_HEADLESS=true
echo ========================================
echo   Legal Document RAG - 本地启动
echo ========================================
echo.
echo 正在启动 Streamlit 应用...
start "" python -m streamlit run app/streamlit_app.py --server.port=8501
timeout /t 5 /nobreak >nul
start http://localhost:8501
echo.
echo 应用已启动！
echo 地址: http://localhost:8501
echo 关闭此窗口即可停止应用
echo ========================================
pause
