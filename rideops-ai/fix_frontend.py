import os

path = "D:/git/rideops-ai/frontend/index.html"
with open(path, "r", encoding="utf-8-sig") as f:
    html = f.read()

# 找到旧的 uploadFile 函数并替换
import re
# 从 "function uploadFile" 或 "async function uploadFile" 开始
# 到第一个 "}" 在顶格结束（函数体结束）
pattern = r'function uploadFile\(file\) \{[\s\S]*?^function '
matches = list(re.finditer(pattern, html, re.MULTILINE))
if matches:
    # 找到 uploadFile 函数
    for m in matches:
        start = m.start()
        end = m.end()
        func_text = html[start:end]
        print(f"找到 uploadFile 函数: {start}-{end}")
        print(f"开头: {func_text[:100]}")
        print(f"结尾: {func_text[-50:]}")
else:
    print("未找到 uploadFile 函数")
