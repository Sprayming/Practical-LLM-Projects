# ============================================
# 手动同步脚本 - 拉取 + 上传
# 双击运行，显示每一步的状态
# ============================================

cd D:\git
$time = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

Write-Host "`n╔══════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║    Git 双向同步                   ║" -ForegroundColor Cyan
Write-Host "╚══════════════════════════════════╝" -ForegroundColor Cyan

# 第1步：拉取
Write-Host "`n📥 拉取远程最新代码 ..." -ForegroundColor Cyan
$pull = & "C:\Program Files\Git\bin\git.exe" pull 2>&1
Write-Host "   $pull" -ForegroundColor Gray

# 第2步：检查本地改动
$status = & "C:\Program Files\Git\bin\git.exe" status --porcelain 2>&1
if ($status) {
    # 有改动 → 自动提交并推送
    $count = ($status -split "`n").Count
    Write-Host "`n📤 检测到 $count 个本地改动，正在同步 ..." -ForegroundColor Yellow
    & "C:\Program Files\Git\bin\git.exe" add . 2>&1 | Out-Null
    $commit = & "C:\Program Files\Git\bin\git.exe" commit -m "Auto sync $time" 2>&1
    Write-Host "   $commit" -ForegroundColor Green

    Write-Host "`n📡 推送到 GitHub ..." -ForegroundColor Cyan
    $push = & "C:\Program Files\Git\bin\git.exe" push 2>&1
    Write-Host "   $push" -ForegroundColor Gray

    Write-Host "`n✅ 同步完成！本地和 GitHub 已保持一致" -ForegroundColor Green
} else {
    Write-Host "`n✅ 没有本地改动，已经是最新版本" -ForegroundColor Green
}

Write-Host "`n按任意键退出 ..." -ForegroundColor Gray
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
