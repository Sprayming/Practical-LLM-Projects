@echo off
cd /d D:\git\legal-doc-rag
set STREAMLIT_EMAIL=
set STREAMLIT_SERVER_HEADLESS=true
start "" python -m streamlit run app/streamlit_app.py --server.port=8501
exit