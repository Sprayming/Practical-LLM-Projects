from typing import List, Dict, Any
from app.models import Order

_datasets: Dict[str, Dict] = {}
_orders: List[Order] = []

def set_datasets(datasets: dict):
    global _datasets
    _datasets = datasets

def get_datasets() -> dict:
    return _datasets

def get_dataset_info() -> dict:
    result = {}
    for name, ds in _datasets.items():
        result[name] = {"count": ds["count"], "columns": ds["columns"]}
    return result

def get_orders():
    return _orders

def set_orders(orders):
    global _orders
    _orders = orders

def clear():
    global _orders, _datasets
    _orders = []
    _datasets = {}
