# ============================================
# RAG 企业知识库 — Lint / 代码检查
# ============================================

$PROJECT_ROOT = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$BACKEND_DIR = Join-Path $PROJECT_ROOT "backend"
$VENV_DIR = Join-Path $BACKEND_DIR ".venv"
$ACTIVATE = Join-Path $VENV_DIR "Scripts\Activate.ps1"
if (Test-Path $ACTIVATE) { . $ACTIVATE }

$exitCode = 0

Write-Host "=== 代码检查 ===" -ForegroundColor Cyan

# ruff — 快速 lint + format 检查
if (Get-Command ruff -ErrorAction SilentlyContinue) {
  Write-Host "[ruff] 检查中 ..." -ForegroundColor Green
  ruff check $BACKEND_DIR/app --output-format github
  if ($LASTEXITCODE -ne 0) { $exitCode = 1 }
} else {
  Write-Host "[ruff] 未安装，跳过 (pip install ruff)" -ForegroundColor Yellow
}

# mypy — 类型检查
if (Get-Command mypy -ErrorAction SilentlyContinue) {
  Write-Host "[mypy] 类型检查中 ..." -ForegroundColor Green
  mypy $BACKEND_DIR/app --strict --ignore-missing-imports
  if ($LASTEXITCODE -ne 0) { $exitCode = 1 }
} else {
  Write-Host "[mypy] 未安装，跳过 (pip install mypy)" -ForegroundColor Yellow
}

if ($exitCode -eq 0) {
  Write-Host "`n✅ 代码检查通过" -ForegroundColor Green
} else {
  Write-Host "`n❌ 代码检查发现问题" -ForegroundColor Red
}

exit $exitCode
