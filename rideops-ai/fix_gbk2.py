import subprocess, time, requests

p = subprocess.Popen(
    ["uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"],
    cwd="D:/git/rideops-ai/backend",
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
)
time.sleep(4)
BASE = "http://127.0.0.1:8000"

# GBK 编码测试 - 带完整错误信息
data = "日期,司机编号,完成单量\n2024-01-01,D001,15".encode("gbk")
print(f"字节数: {len(data)}, 前10字节: {list(data[:10])}")

r = requests.post(BASE + "/api/data/upload", files={"file": ("cn.csv", data)})
print(f"状态码: {r.status_code}")
print(f"响应: {r.text}")

p.terminate()
