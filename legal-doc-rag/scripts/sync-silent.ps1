# ============================================
# Auto sync script
# ============================================

cd D:\git
$time = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
$log = ""

# Step 1: Pull
$pull = & "C:\Program Files\Git\bin\git.exe" pull 2>&1
$log += "`n[Pull] "+$pull

# Step 2: Check changes
$status = & "C:\Program Files\Git\bin\git.exe" status --porcelain 2>&1
if ($status) {
    & "C:\Program Files\Git\bin\git.exe" add . 2>&1 | Out-Null
    $commitMsg = "Auto sync "+$time
    $commit = & "C:\Program Files\Git\bin\git.exe" commit -m $commitMsg 2>&1
    $log += "`n[Commit] "+$commit
    $push = & "C:\Program Files\Git\bin\git.exe" push 2>&1
    $log += "`n[Push] "+$push
} else {
    $log += "`n[Status] No changes"
}

"$time $log" | Add-Content -Path "$env:USERPROFILE\Desktop\sync-log.txt" -Encoding utf8
