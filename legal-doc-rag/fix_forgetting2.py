import os

path = "D:/git/legal-doc-rag/app/memory/forgetting.py"
with open(path, "r", encoding="utf-8") as f:
    lines = f.readlines()

# 找到 import 语句的位置
import_idx = None
for i, line in enumerate(lines):
    if line.startswith("import ") or line.startswith("from "):
        import_idx = i
        break

print(f"共 {len(lines)} 行, 首条 import 在第 {import_idx} 行")
print(f"前5行: {lines[:5]}")
print(f"import 附近: {lines[import_idx-1:import_idx+3]}")

# 修复: 在第1行(标记)后插入 docstring 开头
marker_line = 0
insert_pos = marker_line + 1

# 在 marker 和 import 之间需要 docstring
# 重新构造文件
new_lines = []
new_lines.append(lines[0].rstrip() + "\n")
new_lines.append('\n')
new_lines.append('"""' + "\n")
# docstring 正文: 从第1行(0-indexed)到 import 前
for line in lines[1:import_idx]:
    if line.strip():
        new_lines.append(line)
new_lines.append('"""' + "\n")
new_lines.append("\n")
# import 及之后
for line in lines[import_idx:]:
    new_lines.append(line)

result = "".join(new_lines)
with open(path, "w", encoding="utf-8") as f:
    f.write(result)

# 验证语法
import py_compile
py_compile.compile(path, doraise=True)
print("修复成功, 语法检查通过")

# 验证导入
import sys
sys.path.insert(0, "D:/git/legal-doc-rag")
from app.memory.forgetting import ForgettingMechanism
print(f"ForgettingMechanism 导入成功: {ForgettingMechanism}")
