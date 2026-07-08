import requests, json

BASE = "http://127.0.0.1:8000"

# 1. 健康检查
r = requests.get(f"{BASE}/api/health")
print("=== 健康检查 ===")
print(r.json())

# 2. 上传数据
r = requests.post(f"{BASE}/api/data/upload", files={
    "file": ("orders.csv", open("D:/git/rideops-ai/data/sample/orders_sample.csv", "rb"), "text/csv")
})
print("\n=== 上传数据 ===")
print(json.dumps(r.json(), ensure_ascii=False, indent=2))

# 3. 运行分析
r = requests.post(f"{BASE}/api/analysis/run", params={"date_start": "2024-03-01", "date_end": "2024-03-05"})
data = r.json()
print("\n=== KPI 摘要 ===")
print(json.dumps(data["kpi"], ensure_ascii=False, indent=2))
print(f"\n异常数: {len(data['anomalies'])}")
print(f"AI分析: {data['ai_analysis'][:200]}...")

# 4. 生成报告
r = requests.post(f"{BASE}/api/reports/generate", json={})
rpt = r.json()
print(f"\n=== 报告 ===")
print(f"报告ID: {rpt['report']['id']}")

print("\n=== 全部测试通过 ===")
