import requests, sys

BASE = "http://127.0.0.1:8000"
ok = True

for name, data in [
    ("标准CSV", b"order_id,driver_id,pickup_time,fare\nO001,D001,2024-01-01,38.50"),
    ("中文CSV", "订单号,司机,金额,时间\nC001,D001,38.50,2024-01-01".encode()),
    ("数据文件", open("D:/git/rideops-ai/data/sample/orders_sample.csv", "rb").read()),
]:
    r = requests.post(BASE + "/api/data/upload", files={"file": (name + ".csv", data)})
    d = r.json()
    if d.get("type") in ("orders", "dataset"):
        print(f"通过: {name}")
    else:
        print(f"失败: {name} - {d.get('detail','')}")
        ok = False

print("全部通过" if ok else "有失败")
