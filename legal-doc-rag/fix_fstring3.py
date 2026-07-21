path = "D:/git/legal-doc-rag/app/streamlit_app.py"
with open(path, "r", encoding="utf-8") as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if 'f"' in line and 'Token:' in line:
        print(f"Line {i+1}: {line.strip()[:100]}")
        lines[i] = line.replace('f"', 'f"""', 1).replace('")', '""")')
        print(f"  -> {lines[i].strip()[:100]}")
        break

with open(path, "w", encoding="utf-8") as f:
    f.writelines(lines)

import py_compile
py_compile.compile(path, doraise=True)
print("Syntax OK")
