import os

path = "D:/git/rideops-ai/frontend/index.html"
with open(path, "r", encoding="utf-8-sig") as f:
    html = f.read()

# 找到函数边界
start_marker = "function uploadFile(file) {"
end_marker = "\nfunction loadSummary"

start = html.find(start_marker)
end = html.find(end_marker, start)

if start >= 0 and end > start:
    old_func = html[start:end]
    print(f"找到 uploadFile: {start}-{end}, 长度={len(old_func)}")
    print(f"开头: {old_func[:80]}")
    print(f"结尾: {old_func[-60:]}")
else:
    print(f"未找到: start={start}, end={end}")
