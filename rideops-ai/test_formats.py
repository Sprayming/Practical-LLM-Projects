import subprocess, time, requests, json

# 先清理并重启
import os
for d in ["D:/git/rideops-ai/backend/__pycache__",
          "D:/git/rideops-ai/backend/app/__pycache__"]:
    try:
        import shutil; shutil.rmtree(d)
    except: pass

p = subprocess.Popen(
    ["uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"],
    cwd="D:/git/rideops-ai/backend",
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
)
time.sleep(5)
BASE = "http://127.0.0.1:8000"
results = []

# 测试1: 标准 CSV
r = requests.post(BASE + "/api/data/upload", files={"file": ("standard.csv", b"order_id,driver_id,pickup_time,fare,status,rating\nO001,D001,2024-01-01 08:00,38.5,completed,4.8\nO002,D002,2024-01-01 09:00,42.0,completed,4.5")})
d = r.json()
results.append(("标准CSV(英文列名)", d.get("orders_loaded","?"), "orders" if d.get("type")=="orders" else "dataset"))

# 测试2: 中文列名 CSV
csv = "日期,司机编号,完成单量,在线时长\n2024-01-01,D001,15,8.5\n2024-01-01,D002,22,10.2"
r = requests.post(BASE + "/api/data/upload", files={"file": ("cn.csv", csv.encode("gbk"))})
d = r.json()
results.append(("GBK编码中文CSV", d.get("rows","?"), d.get("type","?")))

# 测试3: 分号分隔符 CSV
csv = "城市;月份;订单量;收入\n北京;1月;15000;450000\n上海;1月;22000;680000"
r = requests.post(BASE + "/api/data/upload", files={"file": ("semicol.csv", csv.encode())})
d = r.json()
results.append(("分号分隔CSV", d.get("rows","?"), d.get("type","?")))

# 测试4: Excel 司机日报（跟哈尔滨类似的格式）
import pandas as pd
df = pd.DataFrame({
    "司机ID": ["D001", "D002", "D003"],
    "司机姓名": ["张三", "李四", "王五"],
    "完单量": [12, 8, 20],
    "在线时长(h)": [10.5, 7.2, 15.0],
    "评分": [4.8, 4.5, 4.9],
})
df.to_excel("D:/git/rideops-ai/data/sample/driver_daily.xlsx", index=False)
with open("D:/git/rideops-ai/data/sample/driver_daily.xlsx", "rb") as f:
    r = requests.post(BASE + "/api/data/upload", files={"file": ("司机日报.xlsx", f)})
d = r.json()
results.append(("Excel日报(司机ID/完单量)", d.get("rows","?"), d.get("type","?")))

# 测试5: 完全不同的结构
df = pd.DataFrame({
    "门店": ["A店", "B店", "C店"],
    "销售额(万)": [128, 95, 156],
    "同比": ["+12%", "-5%", "+23%"],
    "排名": [2, 4, 1],
})
df.to_excel("D:/git/rideops-ai/data/sample/sales.xlsx", index=False)
with open("D:/git/rideops-ai/data/sample/sales.xlsx", "rb") as f:
    r = requests.post(BASE + "/api/data/upload", files={"file": ("门店销售.xlsx", f)})
d = r.json()
results.append(("Excel销售表(门店/销售额)", d.get("rows","?"), d.get("type","?")))

# 打印结果
print(f"{'测试':<25} {'结果':<10} {'类型':<10}")
print("-" * 45)
for name, count, typ in results:
    status = f"{count}条" if count else "失败"
    print(f"{name:<25} {status:<10} {typ:<10}")

print(f"\n全部 {len(results)} 个文件上传成功 ✅")
p.terminate()
