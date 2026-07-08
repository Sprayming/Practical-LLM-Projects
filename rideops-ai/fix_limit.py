# 改上限
path = "D:/git/rideops-ai/backend/app/api/data.py"
with open(path, "r", encoding="utf-8") as f:
    c = f.read()
c = c.replace("MAX_SIZE = 50 * 1024 * 1024", "MAX_SIZE = 500 * 1024 * 1024")
with open(path, "w", encoding="utf-8") as f:
    f.write(c)
print("限制已改为 500MB")

# 重启服务器
import os, subprocess, time
os.system("taskkill /f /im uvicorn.exe 2>nul")
time.sleep(2)
p = subprocess.Popen(["uvicorn","app.main:app","--host","127.0.0.1","--port","8000"], cwd="D:/git/rideops-ai/backend", stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(5)
print("服务器已启动")
