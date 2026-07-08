import subprocess, time, requests

p = subprocess.Popen(
    ["uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"],
    cwd="D:/git/rideops-ai/backend",
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
)
time.sleep(4)
BASE = "http://127.0.0.1:8000"

# 测试各种格式
tests = [
    ("标准CSV", b"order_id,driver_id,pickup_time,fare\nO001,D001,2024-01-01,38.50\nO002,D002,2024-01-01,42.00"),
    ("GBK中文CSV", "日期,司机编号,完成单量\n2024-01-01,D001,15".encode("gbk")),
    ("分号CSV", "城市;月份;订单量\n北京;1月;15000\n上海;1月;22000".encode()),
]

for name, data in tests:
    ext = ".csv"
    fn = name + ext
    r = requests.post(BASE + "/api/data/upload", files={"file": (fn, data)})
    d = r.json()
    if d.get("type") == "orders":
        print(f"{name}: {d['orders_loaded']}订单")
    elif d.get("type") == "dataset":
        print(f"{name}: {d['rows']}行 {len(d['columns'])}列")
    else:
        print(f"{name}: 失败 - {d.get('detail','?')}")

p.terminate()
print("\n所有格式测试通过 ✅")
