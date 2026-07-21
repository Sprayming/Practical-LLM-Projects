path = "D:/git/legal-doc-rag/app/streamlit_app.py"
with open(path, "r", encoding="utf-8") as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if 'f"""' in line and 'Token:' in line:
        lines[i] = line.replace('f"""', 'f"', 1).rstrip() + ')\n'
        break

with open(path, "w", encoding="utf-8") as f:
    f.writelines(lines)

import py_compile
py_compile.compile(path, doraise=True)
print("Syntax OK")
