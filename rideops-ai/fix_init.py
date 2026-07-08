import os

root = "D:/git/rideops-ai/backend/app"

# data/__init__.py
content = (
    'from typing import List, Dict, Any\n'
    'from app.models import Order\n\n'
    '_datasets: Dict[str, Dict] = {}\n'
    '_orders: List[Order] = []\n\n'
    'def set_datasets(datasets: dict):\n'
    '    global _datasets\n'
    '    _datasets = datasets\n\n'
    'def get_datasets() -> dict:\n'
    '    return _datasets\n\n'
    'def get_dataset_info() -> dict:\n'
    '    result = {}\n'
    '    for name, ds in _datasets.items():\n'
    '        result[name] = {"count": ds["count"], "columns": ds["columns"]}\n'
    '    return result\n\n'
    'def get_orders():\n'
    '    return _orders\n\n'
    'def set_orders(orders):\n'
    '    global _orders\n'
    '    _orders = orders\n\n'
    'def clear():\n'
    '    global _orders, _datasets\n'
    '    _orders = []\n'
    '    _datasets = {}\n'
)

p = root + "/data/__init__.py"
with open(p, "w", encoding="utf-8") as f:
    f.write(content)
print("__init__.py OK, size:", os.path.getsize(p), "bytes")

# 验证
with open(p, "r", encoding="utf-8") as f:
    exec(f.read())
print("  验证通过")
