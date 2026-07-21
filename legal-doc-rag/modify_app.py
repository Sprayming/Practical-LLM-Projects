import os

path = "D:/git/legal-doc-rag/app/streamlit_app.py"
with open(path, "r", encoding="utf-8") as f:
    lines = f.readlines()

# 1. 流式输出：修改 API 调用部分
new_api_section = """        placeholder.markdown("Thinking...")
        # 流式输出: 逐字显示 LLM 回答
        resp = requests.post(
            f"{DEEPSEEK_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": full_prompt}],
                "temperature": 0.1,
                "stream": True,
            },
            timeout=60, verify=False, stream=True,
        )
        if resp.status_code == 200:
            answer = ""
            for chunk in resp.iter_lines():
                if chunk:
                    chunk_str = chunk.decode("utf-8")
                    if chunk_str.startswith("data: "):
                        chunk_data = chunk_str[6:]
                        if chunk_data.strip() == "[DONE]":
                            break
                        try:
                            import json
                            delta = json.loads(chunk_data)["choices"][0]["delta"].get("content", "")
                            if delta:
                                answer += delta
                                placeholder.markdown(answer + "\u258c")
                        except Exception:
                            pass
            output_tokens = count_tokens(answer)
            total = input_tokens + output_tokens
            st.session_state.last_tokens = total
            st.session_state.total_tokens += total
            placeholder.markdown(answer + f"\n\\n---\\n*Token: {input_tokens} in + {output_tokens} out = {total}*")
            st.session_state.messages.append({"role": "assistant", "content": answer})
            st.session_state.memory.add("assistant", answer)
            try:
                if "memory" in st.session_state:
                    def memory_llm(p):
                        try:
                            r = requests.post(f"{DEEPSEEK_BASE_URL}/chat/completions",
                                headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"},
                                json={"model": "deepseek-chat", "messages": [{"role": "user", "content": p}], "temperature": 0.1},
                                timeout=15, verify=False)
                            return r.json()["choices"][0]["message"]["content"] if r.status_code == 200 else ""
                        except: return ""
                    st.session_state.memory.async_consolidate(memory_llm)
            except Exception:
                pass
        else:
            placeholder.error(f"API error: {resp.status_code}")
"""

# 找到旧代码的范围并替换
old_marker = "placeholder.markdown(\"Thinking...\")"
for i, line in enumerate(lines):
    if old_marker in line:
        # 找到 try 块开始（上一个紧挨的 try）
        start = i - 1
        while start > 0 and not lines[start].strip().startswith("try:"):
            start -= 1
        # 找到下一个 except 的结束位置
        end = start + 1
        depth = 1
        while end < len(lines) and depth > 0:
            s = lines[end].strip()
            if s.startswith("try:"): depth += 1
            elif s.startswith("except") or s.startswith("finally:"): depth -= 1
            end += 1
            if depth <= 0:
                # 找到对应代码块的结束
                while end < len(lines) and not lines[end].strip().startswith(("if", "st.", "#", "\n", "")):
                    end += 1
                break
        
        # 替换
        new_lines = lines[:start] + [new_api_section] + lines[end:]
        with open(path, "w", encoding="utf-8") as f:
            f.writelines(new_lines)
        print(f"Streaming: replaced lines {start}-{end}")
        break

# 2. 认证：在 st.set_page_config 后插入
with open(path, "r", encoding="utf-8") as f:
    content = f.read()

auth_code = """
# 生产环境认证（可选, 通过 APP_PASSWORD 环境变量开启）
APP_PASSWORD = os.getenv("APP_PASSWORD", "")
if APP_PASSWORD:
    if not st.session_state.get("authenticated"):
        st.title("Legal Document RAG")
        pw = st.text_input("请输入访问密码", type="password")
        if st.button("登录"):
            if pw == APP_PASSWORD:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("密码错误")
        st.stop()

"""

content = content.replace(
    'st.set_page_config(page_title="Legal Document RAG", layout="wide")',
    'st.set_page_config(page_title="Legal Document RAG", layout="wide")' + auth_code
)

# 3. 反馈：在 token 统计行后加按钮
fb_func = """
def _save_feedback(query, answer, rating):
    import json
    fb = {"query": query[:100], "answer": answer[:100], "rating": rating, "timestamp": datetime.now().isoformat()}
    path = "feedback_log.json"
    data = json.loads(open(path, encoding="utf-8").read()) if os.path.exists(path) else []
    data.append(fb)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

"""

fb_buttons = """
            # 用户反馈
            fb_key = f"fb_{len(st.session_state.messages)}"
            c1, c2 = st.columns([1, 1])
            with c1:
                if st.button("\\U0001f44d 有用", key=f"{fb_key}_up"):
                    _save_feedback(prompt, answer, "up")
                    st.toast("\\u2705 \\u611f\\u8c22\\u53cd\\u9988\\uff01")
            with c2:
                if st.button("\\U0001f44e 没用", key=f"{fb_key}_down"):
                    _save_feedback(prompt, answer, "down")
                    st.toast("\\u2705 \\u611f\\u8c22\\u53cd\\u9988\\uff01")
"""

# 插入反馈函数（在 count_tokens 定义后）
content = content.replace(
    "def count_tokens(text: str) -> int:",
    fb_func + "def count_tokens(text: str) -> int:"
)

# 插入反馈按钮（在 token 统计显示后）
content = content.replace(
    'f"\\n\\n---\\n*Token: {input_tokens} in + {output_tokens} out = {total}*"',
    'f"\\n\\n---\\n*Token: {input_tokens} in + {output_tokens} out = {total}*"' + fb_buttons
)

with open(path, "w", encoding="utf-8") as f:
    f.write(content)

print("Auth + Feedback added")
print("Done")
