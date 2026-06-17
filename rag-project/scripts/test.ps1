# ============================================
# RAG 企业知识库 — 测试运行脚本
# ============================================
param(
  [string]$Path = "tests/",
  [switch]$Coverage,
  [string]$Marker
)

$PROJECT_ROOT = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$BACKEND_DIR = Join-Path $PROJECT_ROOT "backend"
$VENV_DIR = Join-Path $BACKEND_DIR ".venv"
$ACTIVATE = Join-Path $VENV_DIR "Scripts\Activate.ps1"
if (Test-Path $ACTIVATE) { . $ACTIVATE }

Write-Host "=== 运行测试 ===" -ForegroundColor Cyan
Write-Host "测试路径: $Path`n"

$cmd = @("python", "-m", "pytest", $Path, "-v")
if ($Coverage) { $cmd += "--cov=app"; $cmd += "--cov-report=term-missing" }
if ($Marker) { $cmd += "-m"; $cmd += $Marker }

& $cmd

exit $LASTEXITCODE
