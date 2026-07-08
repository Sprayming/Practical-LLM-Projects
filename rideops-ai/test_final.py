import subprocess, time, requests, json

proc = subprocess.Popen(
    ["uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"],
    cwd="D:/git/rideops-ai/backend",
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
)
time.sleep(5)

BASE = "http://127.0.0.1:8000"
try:
    r = requests.post(BASE + "/api/data/upload", files={"file": ("orders.csv", open("D:/git/rideops-ai/data/sample/orders_sample.csv", "rb"))})
    print("上传:", r.json()["message"])

    for q in ["最近订单量怎么样？", "哪个时间段订单最多？", "帮我写一份运营简报"]:
        r = requests.post(BASE + "/api/analysis/ask", json={"query": q})
        d = r.json()
        print(f"\n问: {q}")
        print(f"答: {d['answer'][:200]}...")
        print("---")

    print("\n全部通过 ✅")
finally:
    proc.terminate()
