import os

path = "D:/git/rideops-ai/backend/app/api/data.py"
with open(path, "r", encoding="utf-8") as f:
    c = f.read()

# 替换 upload handler 中的不安全 dict 访问
c = c.replace(
    '"orders_loaded": result["orders_loaded"],\n            "drivers_found": result["drivers"],\n            "errors": result.get("warnings", [])[:5],\n            "preview": result["preview"],',
    '"orders_loaded": result.get("orders_loaded", 0),\n            "drivers_found": result.get("drivers", 0),\n            "errors": result.get("warnings", [])[:5],\n            "preview": result.get("preview", []),'
)

with open(path, "w", encoding="utf-8") as f:
    f.write(c)

print("修复完成")
print("验证包含 result.get:")
with open(path, "r", encoding="utf-8") as f:
    for i, line in enumerate(f, 1):
        if "result[" in line and "result.get" not in line and "result.type" not in line:
            if "result[" not in line:
                continue
            print(f"  警告 行{i}: {line.strip()}")
