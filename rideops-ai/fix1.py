# 重写 data/__init__.py
import os
root = "D:/git/rideops-ai/backend/app"

open(root + "/data/__init__.py", "w").write("""
from typing import List
from app.models import Order

_current_columns = []
_current_rows = []
_orders = []

def set_dataset(columns, rows):
    global _current_columns, _current_rows
    _current_columns = columns
    _current_rows = rows

def get_dataset():
    return {"columns": _current_columns, "rows": _current_rows, "count": len(_current_rows)}

def set_orders(orders):
    global _orders
    _orders = orders

def get_orders():
    return _orders

def clear():
    global _orders, _current_columns, _current_rows
    _orders = []
    _current_columns = []
    _current_rows = []
""".strip())

print("data/__init__.py done")
