import os

path = "D:/git/rideops-ai/frontend/index.html"
with open(path, "r", encoding="utf-8-sig") as f:
    html = f.read()

# 找到函数边界
start_marker = "function uploadFile(file) {"
start = html.find(start_marker)

# 查看 uploadFile 后面的内容
idx = html.find("function", start + len(start_marker) + 10)
while idx >= 0:
    # 找到这个函数名
    line_end = html.find("\n", idx)
    line = html[idx:line_end].strip()
    print(f"位置 {idx}: {line}")
    # 下一个 function
    idx = html.find("function", idx + 10)
    if idx > start + 3000:
        break
