import os
p = "D:/git/legal-doc-rag/app/memory/forgetting.py"
with open(p, "r", encoding="utf-8") as f:
    lines = f.readlines()

import_idx = None
for i, l in enumerate(lines):
    if l.startswith("import ") or l.startswith("from "):
        import_idx = i
        break

# 用 hex escape 避免引号冲突
dq = "\x22\x22\x22"
new = []
new.append(lines[0] + "\n")
new.append(dq + "\n")
for l in lines[1:import_idx]:
    new.append(l)
new.append(dq + "\n\n")
for l in lines[import_idx:]:
    new.append(l)

with open(p, "w", encoding="utf-8") as f:
    f.write("".join(new))

import py_compile
py_compile.compile(p, doraise=True)
print("语法正确")
