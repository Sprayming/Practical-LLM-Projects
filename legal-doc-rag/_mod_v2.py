
with open(r"D:\git\legal-doc-rag\app\streamlit_app.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

target_line = 294  # 0-indexed: input_tokens = count_tokens(full_prompt)
assert "input_tokens = count_tokens(full_prompt)" in lines[target_line], f"Line {target_line} mismatch: {repr(lines[target_line])}"
assert "try:" in lines[target_line+1].strip(), f"Line {target_line+1} mismatch: {repr(lines[target_line+1])}"

# Insert cache check block after input_tokens line
# The cache hit path: display, feedback, memory, log, stop
indent = "        "
cache_block = [
    "        import time as _time\n",
    "        _query_start = _time.time()\n",
    "        cached_answer = query_cache.get(full_prompt)\n",
    "        if cached_answer:\n",
    "            output_tokens = count_tokens(cached_answer)\n",
    "            total = input_tokens + output_tokens\n",
    "            st.session_state.last_tokens = total\n",
    "            st.session_state.total_tokens += total\n",
    "            trace.set_tokens(total)\n",
    "            trace.end_span()\n",
    "            trace.print_summary()\n",
    "            get_trace_store().save(trace)\n",
    indent + 'placeholder.markdown(cached_answer + f"\\n\\n---\\n*Token: {input_tokens} in + {output_tokens} out = {total} (cached)*")\n',
    indent + "fb_key = f"fb_{len(st.session_state.messages)}"\n",
    '            c1, c2 = st.columns([1, 1])\n',
    '            with c1:\n',
    '                if st.button("\\U0001f44d \\u6709\\u7528", key=f"{fb_key}_up"):\n',
    '                    _save_feedback(prompt, cached_answer, "up")\n',
    '                    st.toast("\\u2705 \\u611f\\u8c22\\u53cd\\u9988\\uff01")\n',
    '            with c2:\n',
    '                if st.button("\\U0001f44e \\u6ca1\\u7528", key=f"{fb_key}_down"):\n',
    '                    _save_feedback(prompt, cached_answer, "down")\n',
    '                    st.toast("\\u2705 \\u611f\\u8c22\\u53cd\\u9988\\uff01")\n',
    indent + "st.session_state.messages.append({"role": "assistant", "content": cached_answer})\n",
    indent + "st.session_state.memory.add("assistant", cached_answer)\n",
    indent + "st.session_state.memory.extract_entities(prompt, cached_answer, memory_llm)\n",
    indent + "latency_ms = int((_time.time() - _query_start) * 1000)\n",
    indent + "logger.info('query', question=prompt, answer_len=len(cached_answer), tokens=total, latency_ms=latency_ms, cache_hit=True)\n",
    indent + "conv_id = conversation_store.save(st.session_state.messages, conv_id=getattr(st.session_state, 'conv_id', None))\n",
    indent + "st.session_state.conv_id = conv_id\n",
    indent + "st.stop()  # ????????? API ??\n",
]

# Insert after line 294
for j, ins in enumerate(reversed(cache_block)):
    lines.insert(target_line + 1, ins)

# Now find the non-cached flow and add cache.save + log + conversation save
# Look for "st.session_state.memory.extract_entities" in the API path
for i, line in enumerate(lines):
    if "st.session_state.memory.extract_entities(prompt, answer, memory_llm)" in line and i > 320:
        indent2 = line[:len(line) - len(line.lstrip())]
        insert_api = [
            indent2 + "# ???? + ?? + ????????????\n",
            indent2 + "query_cache.set(full_prompt, answer)\n",
            indent2 + "latency_ms = int((_time.time() - _query_start) * 1000)\n",
            indent2 + "logger.info('query', question=prompt, answer_len=len(answer), tokens=total, latency_ms=latency_ms, cache_hit=False)\n",
            indent2 + "conv_id = conversation_store.save(st.session_state.messages, conv_id=getattr(st.session_state, 'conv_id', None))\n",
            indent2 + "st.session_state.conv_id = conv_id\n",
        ]
        for j, ins in enumerate(reversed(insert_api)):
            lines.insert(i + 1, ins)
        break

with open(r"D:\git\legal-doc-rag\app\streamlit_app.py", "w", encoding="utf-8") as f:
    f.writelines(lines)

print("done")
