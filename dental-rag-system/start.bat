@echo off
chcp 65001 >nul
title Dental RAG System

echo ========================================
echo    Dental RAG System - 一键启动
echo ========================================
echo.

:: 检查依赖是否已安装
python -c "import fastapi" 2>nul
if errorlevel 1 (
    echo [1/3] 正在安装依赖...
    pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple/ >nul 2>nul
    if errorlevel 1 (
        pip install -r requirements.txt >nul 2>nul
    )
    echo    依赖安装完成
) else (
    echo [1/3] 依赖已就绪
)

:: 检查 .env，没有则从 .env.example 创建
if not exist .env (
    echo [2/3] 正在创建配置文件...
    copy .env.example .env >nul
    echo    配置文件已创建
) else (
    echo [2/3] 配置已就绪
)

echo [3/3] 启动服务端...
echo.
echo 浏览器将自动打开 http://127.0.0.1:8000/
echo 按 Ctrl+C 停止服务
echo.

:: 打开浏览器
start http://127.0.0.1:8000/

:: 启动服务端
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

pause
