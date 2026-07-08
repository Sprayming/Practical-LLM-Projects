import subprocess, time, requests, os, sys

sys.stdout = open(sys.stdout.fileno(), mode="w", encoding="utf-8", buffering=1)

os.system("taskkill /f /im uvicorn.exe 2>nul")
time.sleep(2)
for d in ["D:/git/rideops-ai/backend/__pycache__","D:/git/rideops-ai/backend/app/__pycache__"]:
    import shutil; shutil.rmtree(d, ignore_errors=True)

p = subprocess.Popen(
    ["uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"],
    cwd="D:/git/rideops-ai/backend",
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
)
time.sleep(5)
BASE = "http://127.0.0.1:8000"

ok, fail = 0, 0

for name, enc, data in [
    ("标准CSV", None, b"order_id,driver_id,pickup_time,fare\nO001,D001,2024-01-01,38.50"),
    ("GBK中文CSV", "gbk", "日期,司机编号,完成单量\n2024-01-01,D001,15"),
    ("分号CSV", None, "城市;月份;订单量\n北京;1月;15000\n上海;1月;22000"),
]:
    if enc: data = data.encode(enc)
    elif isinstance(data, str): data = data.encode()
    r = requests.post(BASE + "/api/data/upload", files={"file": (name + ".csv", data)})
    d = r.json()
    if d.get("type") in ("orders", "dataset"):
        print(f"PASS: {name} (type={d.get('type')}, count={d.get('orders_loaded') or d.get('rows')})")
        ok += 1
    else:
        print(f"FAIL: {name} ({d.get('detail','')[:80]})")
        fail += 1

# 哈尔滨文件
with open("C:/Users/Lenovo/Downloads/哈尔滨完单能力情况摸底.xlsx", "rb") as f:
    r = requests.post(BASE + "/api/data/upload", files={"file": ("hrb.xlsx", f)})
d = r.json()
if d.get("type") == "dataset":
    print(f"PASS: 哈尔滨文件 ({d.get('rows')}行 {len(d.get('columns',[]))}列)")
    ok += 1
else:
    print(f"FAIL: 哈尔滨文件")
    fail += 1

# AI问答
r = requests.post(BASE + "/api/analysis/ask", json={"query": "完单率最低的司机数据有多少行?"})
print(f"AI问答: 回答长度={len(r.json().get('answer',''))}字符")
ok += 1

p.terminate()
print(f"\n结果: {ok}通过 / {fail}失败 ({ok+fail}项)")
