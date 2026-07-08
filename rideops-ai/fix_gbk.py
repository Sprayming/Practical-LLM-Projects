import os

path = "D:/git/rideops-ai/backend/app/data/loader.py"
with open(path, "r", encoding="utf-8") as f:
    content = f.read()

# 把 except (UnicodeDecodeError, UnicodeError) 换成 except Exception
content = content.replace(
    "except (UnicodeDecodeError, UnicodeError):",
    "except Exception:"
)

with open(path, "w", encoding="utf-8") as f:
    f.write(content)

# 测试 GBK CSV
import subprocess, time, requests

p = subprocess.Popen(
    ["uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"],
    cwd="D:/git/rideops-ai/backend",
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
)
time.sleep(4)
BASE = "http://127.0.0.1:8000"

csv = "日期,司机编号,完成单量,在线时长\n2024-01-01,D001,15,8.5\n2024-01-01,D002,22,10.2"
r = requests.post(BASE + "/api/data/upload", files={"file": ("cn.csv", csv.encode("gbk"))})
d = r.json()
print(f"GBK CSV: 状态码={r.status_code}, rows={d.get('rows','?')}, type={d.get('type','?')}")
if r.status_code >= 400:
    print(f"错误: {d.get('detail','')}")

p.terminate()
