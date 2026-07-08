import subprocess, time, requests, json

proc = subprocess.Popen(
    ["uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"],
    cwd="D:/git/rideops-ai/backend",
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
)
time.sleep(5)

BASE = "http://127.0.0.1:8000"
try:
    # 1. 下载模板
    r = requests.get(BASE + "/api/data/template")
    print("=== 模板下载 ===")
    print("状态:", r.status_code)
    if r.status_code == 200:
        print(r.text[:200])

    # 2. 上传正规数据
    r = requests.post(BASE + "/api/data/upload", files={"file": ("orders.csv", open("D:/git/rideops-ai/data/sample/orders_sample.csv", "rb"))})
    d = r.json()
    print(f"\n=== 上传数据 ===")
    print(f"成功: {d.get('success')}, 订单: {d.get('orders_loaded')}, 司机: {d.get('drivers_found')}")
    if d.get("preview"):
        for row in d["preview"][:3]:
            print(f"  预览: {row}")

    # 3. 用中文列名上传
    chinese_csv = "订单号,司机,时间,金额,里程,状态,评分\nC001,D001,2024-04-01 10:00,45.00,15.5,completed,4.8\nC002,D002,2024-04-01 11:00,32.00,10.2,completed,4.5"
    r = requests.post(BASE + "/api/data/upload", files={"file": ("chinese.csv", chinese_csv.encode("utf-8"))})
    d = r.json()
    print(f"\n=== 中文列名上传 ===")
    print(f"成功: {d.get('success')}, 订单: {d.get('orders_loaded')}")
    if d.get("errors"):
        print(f"警告: {d['errors']}")

    # 4. 错误数据测试
    r = requests.post(BASE + "/api/data/upload", files={"file": ("bad.csv", b"name,age\n张三,25")})
    d = r.json()
    print(f"\n=== 错误数据测试 ===")
    if r.status_code >= 400:
        print(f"预期错误: {d.get('detail','')[:100]}")
    else:
        print(f"结果: {d}")

finally:
    proc.terminate()

print("\n测试完成 ✅")
