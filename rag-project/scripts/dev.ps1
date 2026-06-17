# ============================================
# RAG 企业知识库 — 开发服务器启动脚本
# ============================================
param(
  [switch]$Background
)

$ErrorActionPreference = "Continue"
$PROJECT_ROOT = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$BACKEND_DIR = Join-Path $PROJECT_ROOT "backend"

# 激活虚拟环境
$VENV_DIR = Join-Path $BACKEND_DIR ".venv"
if (-not (Test-Path $VENV_DIR)) {
  Write-Host "❌ 虚拟环境未找到，请先运行 .\scripts\setup.ps1" -ForegroundColor Red
  exit 1
}

$ACTIVATE = Join-Path $VENV_DIR "Scripts\Activate.ps1"
if (Test-Path $ACTIVATE) {
  . $ACTIVATE
}

Write-Host "=== 启动 RAG 后端服务器 ===" -ForegroundColor Cyan
Write-Host "     地址: http://127.0.0.1:8000" -ForegroundColor Green
Write-Host "     文档: http://127.0.0.1:8000/docs`n" -ForegroundColor Yellow

if ($Background) {
  Start-Process -NoNewWindow -FilePath "uvicorn" -ArgumentList "app.main:app --host 127.0.0.1 --port 8000 --reload" -WorkingDirectory $BACKEND_DIR
  Write-Host "后端已在后台启动" -ForegroundColor Green
} else {
  uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
}
