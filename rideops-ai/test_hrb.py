import subprocess, time, requests, json

p = subprocess.Popen(
    ["uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"],
    cwd="D:/git/rideops-ai/backend",
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
)
time.sleep(5)
BASE = "http://127.0.0.1:8000"

# 1. 上传哈尔滨文件
print("=== 上传哈尔滨文件 ===")
with open("C:/Users/Lenovo/Downloads/哈尔滨完单能力情况摸底.xlsx", "rb") as f:
    r = requests.post(BASE + "/api/data/upload", files={"file": ("哈尔滨完单能力情况摸底.xlsx", f)})
d = r.json()
print(f"类型: {d.get('type','?')}")
print(f"消息: {d.get('message','')[:200]}")
print(f"行数: {d.get('rows',0)}, 列数: {len(d.get('columns',[]))}")
if d.get("preview"):
    print(f"前2行: {json.dumps(d['preview'][:2], ensure_ascii=False)[:200]}")

# 2. 问问题
print("\n=== AI 问答 ===")
r = requests.post(BASE + "/api/analysis/ask", json={"query": "这些数据是关于什么的？主要有哪些指标？"})
print(f"答: {r.json()['answer'][:400]}...")

# 3. 再问一个业务问题
print("\n=== 业务分析 ===")
r = requests.post(BASE + "/api/analysis/ask", json={"query": "完单率最低的司机是谁？完单量分布如何？"})
print(f"答: {r.json()['answer'][:400]}...")

p.terminate()
print("\n测试完成 ✅")
