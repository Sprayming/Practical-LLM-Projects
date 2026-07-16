@echo off
chcp 65001 >nul
echo ========================================
echo Dental RAG System - 安装脚本
echo ========================================
echo.
echo 1. 安装 Python 依赖...
echo.
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple/
if errorlevel 1 (
    echo.
    echo 清华镜像失败，尝试默认源...
    pip install -r requirements.txt
)
echo.
echo 2. 检查 .env 文件...
if not exist .env (
    copy .env.example .env
    echo 已创建 .env 文件，请编辑填入你的 DeepSeek API Key
) else (
    echo .env 文件已存在
)
echo.
echo ========================================
echo 安装完成！
echo.
echo 启动命令：
echo python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
echo.
echo 浏览器打开 http://127.0.0.1:8000/
echo ========================================
pause
