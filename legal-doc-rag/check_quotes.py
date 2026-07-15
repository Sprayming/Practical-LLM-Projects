p = "D:/git/legal-doc-rag/app/memory/forgetting.py"
with open(p, "r", encoding="utf-8") as f:
    lines = f.readlines()

# 查看行35附近的内容
for i in range(30, 40):
    if i < len(lines):
        print(f"行{i}: {repr(lines[i].rstrip()[:60])}")
