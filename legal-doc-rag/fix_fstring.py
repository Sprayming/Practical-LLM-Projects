import re, py_compile

path = "D:/git/legal-doc-rag/app/streamlit_app.py"
with open(path, "r", encoding="utf-8") as f:
    c = f.read()

# fix broken f-string: find pattern f"...---...Token:..." and wrap with f"""..."""
c = re.sub(
    r'f"(\n+---\n+)\*Token:.*?\*"\)',
    r'f\x22\x22\x22\1*Token: {input_tokens} in + {output_tokens} out = {total}*\x22\x22\x22)',
    c
)

with open(path, "w", encoding="utf-8") as f:
    f.write(c)

py_compile.compile(path, doraise=True)
print("Syntax OK")
