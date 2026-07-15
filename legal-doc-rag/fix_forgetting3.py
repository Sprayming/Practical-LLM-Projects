p = "D:/git/legal-doc-rag/app/memory/forgetting.py"
with open(p, "r", encoding="utf-8") as f:
    lines = f.readlines()

# 查找 import 位置
import_idx = None
for i, l in enumerate(lines):
    if l.startswith("import ") or l.startswith("from "):
        import_idx = i
        break

# 重建文件
new = []
new.append(lines[0])           # marker comment
new.append("\n")
new.append('"""\n')             # open docstring
for l in lines[1:import_idx]:   # docstring content
    new.append(l)
new.append('"""\n')             # close docstring
new.append("\n")
for l in lines[import_idx:]:    # code
    new.append(l)

with open(p, "w", encoding="utf-8") as f:
    f.writelines(new)

# 验证
import py_compile
py_compile.compile(p, doraise=True)
print("语法正确")

import sys
sys.path.insert(0, "D:/git/legal-doc-rag")
from app.memory.forgetting import ForgettingMechanism
print(f"ForgettingMechanism 导入成功: {ForgettingMechanism}")
print(f"  score 方法: {hasattr(ForgettingMechanism, 'score')}")
print(f"  should_forget 方法: {hasattr(ForgettingMechanism, 'should_forget')}")
print(f"  filter_memories 方法: {hasattr(ForgettingMechanism, 'filter_memories')}")
