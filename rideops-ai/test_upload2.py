import requests, sys
BASE = "http://127.0.0.1:8000"

tests = [
    ("标准CSV", b"order_id,driver_id,pickup_time,fare\nO001,D001,2024-01-01,38.50"),
    ("中文CSV", "订单号,司机,金额,时间\nC001,D001,38.50,2024-01-01".encode()),
    ("数据文件", open("D:/git/rideops-ai/data/sample/orders_sample.csv", "rb").read()),
]

all_ok = True
for name, data in tests:
    r = requests.post(BASE + "/api/data/upload", files={"file": (name + ".csv", data)})
    d = r.json()
    ok = d.get("type") in ("orders", "dataset")
    print(f"{'OK' if ok else 'FAIL'} {name}: type={d.get('type')}", end="")
    if d.get("orders_loaded"):
        print(f", {d['orders_loaded']}订单")
    elif d.get("total_rows"):
        print(f", {d['total_rows']}行")
    else:
        print(f", error={d.get('detail','?')}")
    if not ok:
        all_ok = False

if all_ok:
    print("\n全部上传通过")
else:
    print("\n存在问题")
    sys.exit(1)
