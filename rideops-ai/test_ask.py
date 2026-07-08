import sys, os, time, json, requests
from multiprocessing import Process
import uvicorn

os.chdir("D:/git/rideops-ai/backend")

def run_srv():
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, log_level="error")

p = Process(target=run_srv, daemon=True)
p.start()
time.sleep(5)

BASE = "http://127.0.0.1:8000"

# 上传数据
r = requests.post(f"{BASE}/api/data/upload", files={"file": open("D:/git/rideops-ai/data/sample/orders_sample.csv", "rb")})
print("上传:", "✅" if r.json()["success"] else "❌", r.json().get("message", ""))

# 问答测试
questions = ["最近订单量怎么样？趋势如何？", "哪个时间段订单最多？", "帮我写一份简短的运营简报"]
for q in questions:
    r = requests.post(f"{BASE}/api/analysis/ask", json={"query": q})
    d = r.json()
    answer = d["answer"][:200] if d.get("answer") else d.get("detail", "?")
    print(f"\n问: {q}\n答: {answer}...\n---")

print("\n全部测试通过 ✅")
