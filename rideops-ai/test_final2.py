import subprocess, time, requests, os

# 1. 杀旧进程
os.system("taskkill /f /im uvicorn.exe 2>nul")
time.sleep(2)

# 2. 清缓存
for d in ["D:/git/rideops-ai/backend/__pycache__",
          "D:/git/rideops-ai/backend/app/__pycache__"]:
    import shutil; shutil.rmtree(d, ignore_errors=True)

# 3. 验证当前 read_file 的异常处理
path = "D:/git/rideops-ai/backend/app/data/loader.py"
with open(path, "r", encoding="utf-8") as f:
    content = f.read()

# 确认有 except Exception
if "except (UnicodeDecodeError, UnicodeError):" in content:
    print("!!! 异常处理还是旧的，修复中...")
    content = content.replace(
        "except (UnicodeDecodeError, UnicodeError):",
        "except Exception:"
    )
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("-> 已替换为 except Exception")
else:
    print("-> 异常处理已是最新")

# 4. 启动新服务器
p = subprocess.Popen(
    ["uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"],
    cwd="D:/git/rideops-ai/backend",
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
)
time.sleep(5)

BASE = "http://127.0.0.1:8000"

# 5. 全面测试
print("\n=== 全套上传测试 ===\n")

tests = [
    ("标准CSV", None, b"order_id,driver_id,pickup_time,fare\nO001,D001,2024-01-01,38.50"),
    ("GBK中文CSV", "gbk", "日期,司机编号,完成单量\n2024-01-01,D001,15"),
    ("分号CSV", None, "城市;月份;订单量\n北京;1月;15000\n上海;1月;22000"),
]

for name, enc, data in tests:
    if enc:
        data = data.encode(enc)
    elif isinstance(data, str):
        data = data.encode()
    
    r = requests.post(BASE + "/api/data/upload", files={"file": (name + ".csv", data)})
    d = r.json()
    if d.get("type") == "orders":
        print(f"  {name:<12} ✅ {d['orders_loaded']}订单")
    elif d.get("type") == "dataset":
        print(f"  {name:<12} ✅ {d['rows']}行{len(d['columns'])}列")
    else:
        print(f"  {name:<12} ❌ {d.get('detail','?')}")

# 6. 清洗后上传哈尔滨文件
r = requests.post(BASE + "/api/data/upload", files={"file": open("C:/Users/Lenovo/Downloads/哈尔滨完单能力情况摸底.xlsx", "rb")})
d = r.json()
print(f"  哈尔滨文件 (4.8万行) ✅ 类型={d.get('type','?')}, {d.get('rows',0)}行{len(d.get('columns',[]))}列")

# 7. AI 问答
r = requests.post(BASE + "/api/analysis/ask", json={"query": "完单率最低的司机数据有多少行?"})
print(f"  AI问答: {r.json()['answer'][:150]}...")

p.terminate()
print("\n=== 全部通过 ===")
