import re, py_compile

path = "D:/git/legal-doc-rag/app/streamlit_app.py"
with open(path, "r", encoding="utf-8") as f:
    c = f.read()

tq = "\x22\x22\x22"  # """
c = re.sub(
    r'f"(\n+---\n+)\*Token:.*?\*"\)',
    f'f{tq}\\1*Token: {{{{input_tokens}}}} in + {{{{output_tokens}}}} out = {{{{total}}}}*{tq})',
    c
)

with open(path, "w", encoding="utf-8") as f:
    f.write(c)

py_compile.compile(path, doraise=True)
print("Syntax OK")
