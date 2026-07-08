# 测试 GBK CSV 具体是什么错误
import requests
BASE = "http://127.0.0.1:8000"

csv = "日期,司机编号,完成单量,在线时长\n2024-01-01,D001,15,8.5\n2024-01-01,D002,22,10.2"
r = requests.post(BASE + "/api/data/upload", files={"file": ("cn.csv", csv.encode("gbk"))})
print("状态码:", r.status_code)
print("响应:", r.text[:500])
