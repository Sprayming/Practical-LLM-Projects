# ============================================
# 自动同步脚本（静默版 - 给计划任务用）
# 每整点拉取 GitHub 最新 + 自动上传本地改动
# ============================================

cd D:\git
$time = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
$log = ""

# 第1步：拉取远程最新代码
$pull = & "C:\Program Files\Git\bin\git.exe" pull 2>&1
$log += "`n[拉取] $pull"

# 第2步：检查本地是否有改动
$status = & "C:\Program Files\Git\bin\git.exe" status --porcelain 2>&1
if ($status) {
    # 有改动 → 提交并推送
    & "C:\Program Files\Git\bin\git.exe" add . 2>&1 | Out-Null
    $commitMsg = "Auto sync $time"
    $commit = & "C:\Program Files\Git\bin\git.exe" commit -m $commitMsg 2>&1
    $log += "`n[提交] $commit"
    $push = & "C:\Program Files\Git\bin\git.exe" push 2>&1
    $log += "`n[推送] $push"
} else {
    $log += "`n[状态] 无本地改动"
}

# 写入桌面日志
"[$time] $log" | Add-Content -Path "$env:USERPROFILE\Desktop\sync-log.txt" -Encoding utf8
