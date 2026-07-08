import subprocess, time, requests

p = subprocess.Popen(
    ["uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"],
    cwd="D:/git/rideops-ai/backend",
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
)
time.sleep(5)
BASE = "http://127.0.0.1:8000"

# 模板
r = requests.get(BASE + "/api/data/template")
print("模板:", r.status_code, r.text[:80])

# 正规CSV
r = requests.post(BASE + "/api/data/upload", files={"file": ("orders.csv", open("D:/git/rideops-ai/data/sample/orders_sample.csv", "rb"))})
d = r.json()
print("正规:", d["orders_loaded"], "订单")

# 中文列名CSV
csv = "订单号,司机,时间,金额,里程,状态,评分\nC001,D001,2024-04-01 10:00,45.00,15.5,completed,4.8\nC002,D002,2024-04-01 11:00,32.00,10.2,completed,4.5"
r = requests.post(BASE + "/api/data/upload", files={"file": ("cn.csv", csv.encode())})
d = r.json()
print("中文:", d["orders_loaded"], "订单")

# 问答
r = requests.post(BASE + "/api/analysis/ask", json={"query": "哪个时间段订单最多?"})
print("问答:", r.json()["answer"][:150])

p.terminate()
print("=== OK ===")
