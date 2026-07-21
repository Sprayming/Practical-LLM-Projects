
with open(r"D:\git\legal-doc-rag\app\streamlit_app.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

# Find the line with input_tokens
input_tokens_idx = None
for i, line in enumerate(lines):
    if "input_tokens = count_tokens(full_prompt)" in line:
        input_tokens_idx = i
        break

if input_tokens_idx is None:
    print("ERROR: input_tokens line not found")
    exit(1)

print(f"Found input_tokens at line {input_tokens_idx + 1}")

# Build lines to insert for cache check + all processing including st.stop()
# Using raw strings to avoid escaping hell, then constructing step by step
xq = chr(34)  # double quote
sq = chr(39)  # single quote

cache_lines = [
    "        import time as _time",
    "        _query_start = _time.time()",
    "        cached_answer = query_cache.get(full_prompt)",
    "        if cached_answer:",
    "            output_tokens = count_tokens(cached_answer)",
    "            total = input_tokens + output_tokens",
    "            st.session_state.last_tokens = total",
    "            st.session_state.total_tokens += total",
    "            trace.set_tokens(total)",
    "            trace.end_span()",
    "            trace.print_summary()",
    "            get_trace_store().save(trace)",
    f"            placeholder.markdown(cached_answer + f{xq}\n\n---\n*Token: {input_tokens} in + {output_tokens} out = {total} (cached)*{xq})",
    f"            fb_key = f{xq}fb_{xq}+str(len(st.session_state.messages))",
    "            c1, c2 = st.columns([1, 1])",
    "            with c1:",
    f"                if st.button({xq}\U0001f44d \u6709\u7528{xq}, key=f{xq}{fb_key_up}{xq}):",
    f"                    _save_feedback(prompt, cached_answer, {xq}up{xq})",
    f"                    st.toast({xq}\u2705 \u611f\u8c22\u53cd\u9988\uff01{xq})",
    "            with c2:",
    f"                if st.button({xq}\U0001f44e \u6ca1\u7528{xq}, key=f{xq}{fb_key_down}{xq}):",
    f"                    _save_feedback(prompt, cached_answer, {xq}down{xq})",
    f"                    st.toast({xq}\u2705 \u611f\u8c22\u53cd\u9988\uff01{xq})",
    f"            st.session_state.messages.append({xq}role{xq}: {xq}assistant{xq}, {xq}content{xq}: {xq}cached_answer{xq})",
    f'            st.session_state.memory.add("assistant", cached_answer)',
    "            st.session_state.memory.extract_entities(prompt, cached_answer, memory_llm)",
    "            latency_ms = int((_time.time() - _query_start) * 1000)",
    f"            logger.info({xq}query{xq}, question=prompt, answer_len=len(cached_answer), tokens=total, latency_ms=latency_ms, cache_hit=True)",
    "            conv_id = conversation_store.save(st.session_state.messages, conv_id=getattr(st.session_state, f{xq}conv_id{xq}, None))",
    "            st.session_state.conv_id = conv_id",
    "            st.stop()",
]

# Insert cache lines after input_tokens line
for j, ins in enumerate(reversed(cache_lines)):
    lines.insert(input_tokens_idx + 1, ins + "\n")

print(f"Inserted {len(cache_lines)} cache check lines")

# Find the second occurrence of extract_entities for API path
first_idx = None
second_idx = None
marker = "st.session_state.memory.extract_entities(prompt, answer, memory_llm)"
for i, line in enumerate(lines):
    if marker in line:
        if first_idx is None:
            first_idx = i
        else:
            second_idx = i
            break

if second_idx is not None:
    api_insert = [
        f"                # production: cache + log + conversation save",
        f"                query_cache.set(full_prompt, answer)",
        f"                latency_ms = int((_time.time() - _query_start) * 1000)",
        f"                logger.info({xq}query{xq}, question=prompt, answer_len=len(answer), tokens=total, latency_ms=latency_ms, cache_hit=False)",
        f"                conv_id = conversation_store.save(st.session_state.messages, conv_id=getattr(st.session_state, f{xq}conv_id{xq}, None))",
        f"                st.session_state.conv_id = conv_id",
    ]
    for j, ins in enumerate(reversed(api_insert)):
        lines.insert(second_idx + 1, ins + "\n")
    print(f"Inserted {len(api_insert)} API integration lines at line {second_idx + 1}")
else:
    print("WARNING: second occurrence of api marker not found")

with open(r"D:\git\legal-doc-rag\app\streamlit_app.py", "w", encoding="utf-8") as f:
    f.writelines(lines)

print("done")
