path = "D:/git/legal-doc-rag/app/streamlit_app.py"
with open(path, "r", encoding="utf-8") as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if '+ f"' in line and 'Token' not in line:
        indent = line[:len(line) - len(line.lstrip())]
        correct = indent + line.strip() + '\\n\\n---\\n*Token: {input_tokens} in + {output_tokens} out = {total}*")\n'
        lines[i] = correct
        del lines[i+1]
        break

with open(path, "w", encoding="utf-8") as f:
    f.writelines(lines)

import py_compile
py_compile.compile(path, doraise=True)
print("Syntax OK")
