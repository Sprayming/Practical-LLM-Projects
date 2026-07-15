import os

path = "D:/git/legal-doc-rag/app/memory/forgetting.py"
with open(path, "r", encoding="utf-8") as f:
    content = f.read()

# 检查第3行
lines = content.split("\n")
print("第1行:", repr(lines[0][:40]))
print("第2行:", repr(lines[1]))
print("第3行:", repr(lines[2][:20]))
print("第4行:", repr(lines[3][:40]))

# 如果 docstring 被转义了, 修复
content = content.replace('\\"\\"\\"', '\"\"\"')
with open(path, "w", encoding="utf-8") as f:
    f.write(content)

# 验证修复
import py_compile
py_compile.compile(path, doraise=True)
print("修复后语法检查通过")
