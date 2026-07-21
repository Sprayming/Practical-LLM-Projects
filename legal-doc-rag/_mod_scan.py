
import re

path = r"D:\git\legal-doc-rag\app\streamlit_app.py"
with open(path, "r", encoding="utf-8") as f:
    raw = f.read()

# find the key insertion points
lines = raw.split("\n")
print(f"total lines: {len(lines)}")

# Find line with "input_tokens = count_tokens(full_prompt)"
for i, line in enumerate(lines):
    if "input_tokens = count_tokens(full_prompt)" in line:
        print(f"input_tokens at line {i+1}: {repr(line)}")
    if "if resp.status_code == 200:" in line:
        print(f"status check at line {i+1}: {repr(line)}")
    if "placeholder.markdown(answer" in line and "Token" in line:
        print(f"placeholder at line {i+1}: {repr(line)}")
    if "# ????" in line:
        print(f"shadow extract at line {i+1}: {repr(line)}")
    if "st.rerun()" in line:
        print(f"st.rerun at line {i+1}: {repr(line)}")

print("--- scan complete ---")
