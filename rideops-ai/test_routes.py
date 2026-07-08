import subprocess, time, requests, json

proc = subprocess.Popen(
    ["uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"],
    cwd="D:/git/rideops-ai/backend",
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
)
time.sleep(5)

BASE = "http://127.0.0.1:8000"

# 1. 所有路由列表
r = requests.get(BASE + "/openapi.json")
if r.status_code == 200:
    paths = list(r.json().get("paths", {}).keys())
    print("可用路由:", paths)
else:
    print("API 文档无法访问:", r.status_code)
    # 尝试直接上传
    r = requests.post(BASE + "/api/data/upload", files={"file": ("test.csv", b"order_id,driver_id,pickup_time,fare\nT001,D001,2024-01-01 08:00,38.50")})
    print(r.status_code, r.text[:200])

finally:
    proc.terminate()

print("\n检查完成")
