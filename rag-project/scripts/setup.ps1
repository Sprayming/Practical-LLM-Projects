# ============================================
# RAG 企业知识库 — 开发环境初始化脚本
# ============================================
param(
  [switch]$Force
)

$ErrorActionPreference = "Stop"
$PROJECT_ROOT = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$BACKEND_DIR = Join-Path $PROJECT_ROOT "backend"
$FRONTEND_DIR = Join-Path $PROJECT_ROOT "frontend"

Write-Host "=== RAG 企业知识库 — 环境初始化 ===" -ForegroundColor Cyan
Write-Host "项目路径: $PROJECT_ROOT`n"

# ── 1. Python 虚拟环境 ──────────────────────────
$VENV_DIR = Join-Path $BACKEND_DIR ".venv"
if (-not (Test-Path $VENV_DIR)) {
  Write-Host "[1/4] 创建 Python 虚拟环境 ..." -ForegroundColor Green
  python -m venv $VENV_DIR
} else {
  Write-Host "[1/4] Python 虚拟环境已存在，跳过" -ForegroundColor Yellow
}

# ── 2. 安装依赖 ─────────────────────────────────
Write-Host "[2/4] 安装 Python 依赖 ..." -ForegroundColor Green
& (Join-Path $VENV_DIR "Scripts\pip") install -r (Join-Path $BACKEND_DIR "requirements.txt")

# ── 3. .env 检查 ────────────────────────────────
$ENV_FILE = Join-Path $BACKEND_DIR ".env"
if (-not (Test-Path $ENV_FILE)) {
  Write-Host "[3/4] 创建 .env 文件 ..." -ForegroundColor Green
  Copy-Item (Join-Path $BACKEND_DIR ".env.example") $ENV_FILE -Force
  Write-Host "      ⚠️  请编辑 $ENV_FILE 填入你的 OPENAI_API_KEY" -ForegroundColor Yellow
} else {
  Write-Host "[3/4] .env 文件已存在，跳过" -ForegroundColor Yellow
}

# ── 4. 创建运行时目录 ───────────────────────────
Write-Host "[4/4] 创建运行时目录 ..." -ForegroundColor Green
$null = New-Item -ItemType Directory -Force -Path (Join-Path $BACKEND_DIR "uploads")
$null = New-Item -ItemType Directory -Force -Path (Join-Path $BACKEND_DIR "chroma_db")

Write-Host "`n=== 初始化完成 ===" -ForegroundColor Cyan
Write-Host "使用 .\scripts\dev.ps1 启动开发服务器" -ForegroundColor Green
