
with open(r"D:\git\legal-doc-rag\app\streamlit_app.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

# Line 294 (0-indexed): "        input_tokens = count_tokens(full_prompt)\n"
# Insert cache check + timing after line 294, and wrap the try block

insert_after_294 = [
    "        import time as _time\n",
    "        _query_start = _time.time()\n",
    "        cached_answer = query_cache.get(full_prompt)\n",
    "        if not cached_answer:\n",
]
# Insert at position 295 (after line 294)
for j, ins in enumerate(insert_after_294):
    lines.insert(295 + j, ins)

# Now adjust line 295 (now shifted by 4 to position 299): "        try:\n" 
# Need to indent it further and wrap
# The original line 295 "        try:\n" is now at index 299
# Change "        try:\n" to "            try:\n"
for i, line in enumerate(lines):
    if line.strip() == "try:" and i > 290 and i < 310:
        lines[i] = "            try:\n"
        break

# Change "    # ?? DeepSeek API\n" to "    # ?? DeepSeek API\n" ? already has correct indent for inside `if not cached_answer`
# But it needs to be inside the try block, so indent it one more level
for i, line in enumerate(lines):
    if i > 295 and i < 320 and "?? DeepSeek API" in line:
        indent = line[:len(line) - len(line.lstrip())]
        lines[i] = "                " + line.lstrip()
        break

# Find "if resp.status_code == 200:" at the right section and change it
for i, line in enumerate(lines):
    if line.strip() == "if resp.status_code == 200:" and i > 300 and i < 325:
        lines[i] = "            if cached_answer or resp.status_code == 200:\n"
        break

# Find the answer assignment line and wrap with if/else for cached vs API
for i, line in enumerate(lines):
    if i > 300 and i < 330 and "data = resp.json()" in line:
        # Change: "                data = resp.json()" ? "                if not cached_answer:\n                    data = resp.json()"
        indent = line[:len(line) - len(line.lstrip())]
        lines[i] = indent + "if not cached_answer:\n"
        lines.insert(i+1, indent + "    data = resp.json()\n")
        lines.insert(i+2, indent + "    answer = 'Unexpected response format'\n")
        # Find the next few lines and handle the answer extraction
        for j in range(i+3, min(i+10, len(lines))):
            if "answer = data" in lines[j]:
                indent2 = lines[j][:len(lines[j]) - len(lines[j].lstrip())]
                lines[j] = indent2 + "answer = data['choices'][0]['message']['content'] or 'Empty response'\n"
            elif "answer = " in lines[j] and "Unexpected" in lines[j]:
                # Remove this line as we handle it above
                pass
        break

# Add (cached) indicator to the placeholder markdown
for i, line in enumerate(lines):
    if "placeholder.markdown(answer" in line and "Token" in line and i > 310 and i < 345:
        # Add suffix "(cached)" after cached_answer
        indent = line[:len(line) - len(line.lstrip())]
        old_end = ' out = {total}*")'
        new_end = ' out = {total}' + (' (cached)' if cached_answer else '') + '*")'
        lines[i] = line.replace(old_end, new_end)
        break

# After the feedback buttons block, add logging + cache.save + conversation.save
# Find the stray ")" line and insert before it
for i, line in enumerate(lines):
    if line.strip() == ")" and i > 325 and i < 345:
        indent = "                "
        insert_block = [
            "            # ??????\n",
            indent + "if not cached_answer:\n",
            indent + "    query_cache.set(full_prompt, answer)\n",
            indent + "latency_ms = int((_time.time() - _query_start) * 1000)\n",
            indent + "logger.info('query', question=prompt, answer_len=len(answer), tokens=total, latency_ms=latency_ms, cache_hit=bool(cached_answer))\n",
            indent + "conv_id = conversation_store.save(st.session_state.messages, conv_id=getattr(st.session_state, 'conv_id', None))\n",
            indent + "st.session_state.conv_id = conv_id\n",
        ]
        for j, ins in enumerate(insert_block):
            lines.insert(i + j, ins)
        break

# Add the else clause for `if not cached_answer:` after the except block
for i, line in enumerate(lines):
    if line.strip().startswith("except Exception as e:") and i > 335:
        # Add a reduced cache-hit handler (just blank, the cached flow is handled by modifying if/else above)
        indent = line[:len(line) - len(line.lstrip())]
        lines.insert(i, "        else:\n")
        lines.insert(i+1, "            # ???????????????????\n")
        lines.insert(i+2, "            pass\n")
        break

with open(r"D:\git\legal-doc-rag\app\streamlit_app.py", "w", encoding="utf-8") as f:
    f.writelines(lines)

print("done")
