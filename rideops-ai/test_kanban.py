import os, requests
BASE = "http://127.0.0.1:8000"
f = "D:/日看板/活动效果监控/2026版日常数据看板.xlsx"
print("文件大小:", os.path.getsize(f)/1024/1024, "MB")

# 先检查 pd 能不能读
import pandas as pd
try:
    xl = pd.ExcelFile(f)
    print("Sheet数:", len(xl.sheet_names))
    print("前5Sheet:", xl.sheet_names[:5])
except Exception as e:
    print("pandas 读取失败:", e)

# 上传
r = requests.post(BASE + "/api/data/upload", files={"file": open(f, "rb")}, timeout=180)
d = r.json()
print("\n状态码:", r.status_code)
print("响应:", d)
