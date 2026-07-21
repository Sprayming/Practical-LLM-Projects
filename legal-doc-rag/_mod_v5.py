with open(r"D:\git\legal-doc-rag\app\streamlit_app.py", "r", encoding="utf-8") as f:
    txt = f.read()

# --- Cache check block to insert after input_tokens ---
cache_check = '''
        import time as _time
        _query_start = _time.time()
        cached_answer = query_cache.get(full_prompt)
        if cached_answer:
            output_tokens = count_tokens(cached_answer)
            total = input_tokens + output_tokens
            st.session_state.last_tokens = total
            st.session_state.total_tokens += total
            trace.set_tokens(total)
            trace.end_span()
            trace.print_summary()
            get_trace_store().save(trace)
            placeholder.markdown(cached_answer + f"\n\n---\n*Token: {input_tokens} in + {output_tokens} out = {total} (cached)*")
            fb_key = "fb_" + str(len(st.session_state.messages))
            c1, c2 = st.columns([1, 1])
            with c1:
                if st.button("\U0001f44d \u6709\u7528", key=fb_key + "_up"):
                    _save_feedback(prompt, cached_answer, "up")
                    st.toast("\u2705 \u611f\u8c22\u53cd\u9988\uff01")
            with c2:
                if st.button("\U0001f44e \u6ca1\u7528", key=fb_key + "_down"):
                    _save_feedback(prompt, cached_answer, "down")
                    st.toast("\u2705 \u611f\u8c22\u53cd\u9988\uff01")
            st.session_state.messages.append({"role": "assistant", "content": cached_answer})
            st.session_state.memory.add("assistant", cached_answer)
            st.session_state.memory.extract_entities(prompt, cached_answer, memory_llm)
            latency_ms = int((_time.time() - _query_start) * 1000)
            logger.info("query", question=prompt, answer_len=len(cached_answer), tokens=total, latency_ms=latency_ms, cache_hit=True)
            conv_id = conversation_store.save(st.session_state.messages, conv_id=getattr(st.session_state, "conv_id", None))
            st.session_state.conv_id = conv_id
            st.stop()
'''

target = '        input_tokens = count_tokens(full_prompt)'
txt = txt.replace(target, target + cache_check, 1)

# --- API path integration ---
api_marker = 'st.session_state.memory.extract_entities(prompt, answer, memory_llm)'
api_insert = '''                # 生产集成：缓存 + 日志 + 对话持久化
                query_cache.set(full_prompt, answer)
                latency_ms = int((_time.time() - _query_start) * 1000)
                logger.info("query", question=prompt, answer_len=len(answer), tokens=total, latency_ms=latency_ms, cache_hit=False)
                conv_id = conversation_store.save(st.session_state.messages, conv_id=getattr(st.session_state, "conv_id", None))
                st.session_state.conv_id = conv_id
'''
first_idx = txt.find(api_marker)
if first_idx >= 0:
    second_idx = txt.find(api_marker, first_idx + 1)
    if second_idx >= 0:
        txt = txt[:second_idx] + api_insert + txt[second_idx:]

with open(r"D:\git\legal-doc-rag\app\streamlit_app.py", "w", encoding="utf-8") as f:
    f.write(txt)
print("done")
if first_idx < 0:
    print("WARNING: api_marker not found")
elif second_idx < 0:
    print("WARNING: only one occurrence found - API path NOT modified")
else:
    print(f"OK: cache at idx {first_idx}, API integration at idx {second_idx}")