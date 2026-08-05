# ============================================
# Auto sync script
# ============================================

cd D:\git
$time = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
$log = ""

# Step 0: 提高 http 缓冲区，避免大推送被服务端中断
& "C:\Program Files\Git\bin\git.exe" config http.postBuffer 524288000 2>&1 | Out-Null

# Step 1: Pull
$pull = & "C:\Program Files\Git\bin\git.exe" pull 2>&1
$log += "`n[Pull] "+$pull

# Step 2: Check changes
$status = & "C:\Program Files\Git\bin\git.exe" status --porcelain 2>&1
if ($status) {
    # 保险：若大文件(*.tar)被意外跟踪，从索引移除并提示检查 .gitignore
    $trackedTar = & "C:\Program Files\Git\bin\git.exe" ls-files | Select-String "\.tar$"
    if ($trackedTar) {
        & "C:\Program Files\Git\bin\git.exe" rm --cached --ignore-unmatch ($trackedTar -split "`n") 2>&1 | Out-Null
        $log += "`n[Warn] 发现被跟踪的大文件(*.tar)，已从索引移除，请确认 .gitignore 已排除"
    }
    & "C:\Program Files\Git\bin\git.exe" add -A 2>&1 | Out-Null
    $commitMsg = "Auto sync "+$time
    $commit = & "C:\Program Files\Git\bin\git.exe" commit -m $commitMsg 2>&1
    $log += "`n[Commit] "+$commit
    # 推送带重试，避免瞬时网络中断导致静默失败
    $max=3; $attempt=0; $ok=$false
    while ($attempt -lt $max -and -not $ok) {
        $push = & "C:\Program Files\Git\bin\git.exe" push 2>&1
        if ($LASTEXITCODE -eq 0) { $ok=$true; $log += "`n[Push] SUCCESS`n"+$push }
        else { $attempt++; $log += "`n[Push attempt $attempt failed]`n"+$push; Start-Sleep -Seconds 2 }
    }
    if (-not $ok) { $log += "`n[Push] FAILED after $max attempts" }
} else {
    $log += "`n[Status] No changes"
}

"$time $log" | Add-Content -Path "$env:USERPROFILE\Desktop\sync-log.txt" -Encoding utf8
