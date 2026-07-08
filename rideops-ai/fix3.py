import os

root = "D:/git/rideops-ai/backend/app"

loader_code = r'''
"""
数据加载器 — 支持多种格式和任意列名
1. 如果列名能匹配订单模型 → 解析为 Order 对象
2. 如果完全不匹配 → 存储为通用数据集（供 AI 分析）
"""
import pandas as pd
from pathlib import Path
from datetime import datetime
from app.models import Order
from app.data import set_orders, set_dataset

SUPPORTED_FORMATS = {".csv", ".xlsx", ".xls"}

# 列名映射（宽松匹配）
COLUMN_MAP = {
    "order_id": "order_id", "订单号": "order_id", "订单id": "order_id",
    "driver_id": "driver_id", "司机id": "driver_id", "司机编号": "driver_id", "司机": "driver_id",
    "passenger_id": "passenger_id", "乘客id": "passenger_id",
    "pickup_time": "pickup_time", "时间": "pickup_time", "接单时间": "pickup_time",
    "pickup_location": "pickup_location", "出发地": "pickup_location",
    "dropoff_location": "dropoff_location", "目的地": "dropoff_location",
    "distance_km": "distance_km", "里程": "distance_km", "距离": "distance_km",
    "duration_min": "duration_min", "时长": "duration_min",
    "fare": "fare", "金额": "fare", "费用": "fare", "车费": "fare", "乘客应付金额": "fare",
    "status": "status", "状态": "status", "订单状态": "status",
    "rating": "rating", "评分": "rating", "评价": "rating",
    "date": "pickup_time", "日期": "pickup_time", "日期(天)": "pickup_time",
}

def read_file(file_path):
    ext = Path(file_path).suffix.lower()
    if ext not in SUPPORTED_FORMATS:
        raise ValueError(f"不支持的文件格式: {ext}")
    if ext == ".csv":
        return pd.read_csv(file_path, encoding="utf-8")
    else:
        return pd.read_excel(file_path, sheet_name=0)

def normalize_columns(df):
    renamed = {}
    for col in df.columns:
        c = col.strip()
        if c in COLUMN_MAP:
            renamed[col] = COLUMN_MAP[c]
        elif c.lower() in COLUMN_MAP:
            renamed[col] = COLUMN_MAP[c.lower()]
    return df.rename(columns=renamed)

def parse_as_orders(df):
    """尝试把 DataFrame 解析为订单列表"""
    df = normalize_columns(df)
    needed = ["order_id", "driver_id"]
    missing = [c for c in needed if c not in df.columns]
    if missing:
        return None, ["无法识别为订单数据"]

    orders, errors = [], []
    for idx, row in df.iterrows():
        try:
            pt = row.get("pickup_time")
            if pd.isna(pt): pt = datetime.now()
            else: pt = pd.to_datetime(pt)

            orders.append(Order(
                order_id=str(row.get("order_id", f"R{idx}")),
                driver_id=str(row.get("driver_id", "")),
                passenger_id=str(row.get("passenger_id", "")) if pd.notna(row.get("passenger_id", "")) else "",
                pickup_time=pt,
                pickup_location=str(row.get("pickup_location", "")) if pd.notna(row.get("pickup_location", "")) else "",
                dropoff_location=str(row.get("dropoff_location", "")) if pd.notna(row.get("dropoff_location", "")) else "",
                distance_km=float(row.get("distance_km", 0)) if pd.notna(row.get("distance_km", 0)) else 0.0,
                duration_min=int(row.get("duration_min", 0)) if pd.notna(row.get("duration_min", 0)) else 0,
                fare=float(row.get("fare", 0)),
                status=str(row.get("status", "completed")),
                rating=float(row["rating"]) if pd.notna(row.get("rating")) else None,
            ))
        except Exception as e:
            errors.append(f"第{idx+2}行: {e}")
    return orders, errors

def parse_as_dataset(df):
    """把任意 DataFrame 存为通用数据集"""
    rows = df.where(df.notna(), None).to_dict(orient="records")
    columns = list(df.columns)
    set_dataset(columns, rows)
    return columns, rows

def load_any_file(file_path):
    """加载任意文件，自动识别格式"""
    df = read_file(file_path)
    if df.empty:
        raise ValueError("文件为空，没有数据")

    # 优先尝试解析为订单
    orders, errors = parse_as_orders(df)

    if orders is not None and len(orders) > 0:
        set_orders(orders)
        return {
            "type": "orders",
            "orders_loaded": len(orders),
            "errors": errors,
            "drivers": len(set(o.driver_id for o in orders)),
            "preview": [{"order_id": o.order_id, "driver_id": o.driver_id, "fare": o.fare, "status": o.status} for o in orders[:5]],
        }
    else:
        # 存为通用数据集
        columns, rows = parse_as_dataset(df)
        return {
            "type": "dataset",
            "rows": len(rows),
            "columns": columns,
            "errors": errors,
            "preview": rows[:5],
        }

def generate_template():
    return "order_id,driver_id,passenger_id,pickup_time,pickup_location,dropoff_location,distance_km,duration_min,fare,status,rating\nOR001,DRV001,PAS001,2024-01-01 08:30,\u671d\u9633\u533a,\u6d77\u6dc0\u533a,12.5,32,38.50,completed,4.8\n"
'''

with open(root + "/data/loader.py", "w", encoding="utf-8") as f:
    f.write(loader_code.strip())

print("loader.py 已重写")
