"""
数据加载器 — 支持多 Sheet Excel + 自动列名映射
"""
import pandas as pd
from pathlib import Path
from datetime import datetime
from typing import List, Tuple
from app.models import Order
from app.data import set_orders, set_datasets

SUPPORTED_FORMATS = {".csv", ".xlsx", ".xls"}

COLUMN_MAP = {
    "order_id": "order_id", "订单号": "order_id",
    "driver_id": "driver_id", "司机id": "driver_id", "司机编号": "driver_id", "司机": "driver_id",
    "passenger_id": "passenger_id", "乘客id": "passenger_id",
    "pickup_time": "pickup_time", "时间": "pickup_time", "接单时间": "pickup_time", "日期": "pickup_time",
    "pickup_location": "pickup_location", "出发地": "pickup_location",
    "dropoff_location": "dropoff_location", "目的地": "dropoff_location",
    "distance_km": "distance_km", "里程": "distance_km",
    "duration_min": "duration_min", "时长": "duration_min",
    "fare": "fare", "金额": "fare", "费用": "fare", "车费": "fare", "订单金额": "fare",
    "status": "status", "状态": "status",
    "rating": "rating", "评分": "rating",
    "date": "pickup_time", "日期(天)": "pickup_time",
}

def read_file(file_path, sheet_name=0):
    ext = Path(file_path).suffix.lower()
    if ext not in SUPPORTED_FORMATS:
        raise ValueError(f"不支持的文件格式: {ext}")
    if ext == ".csv":
        for enc in ["utf-8", "gbk", "gb2312", "latin-1"]:
            try: return pd.read_csv(file_path, encoding=enc)
            except Exception: continue
        for sep in [",", ";", "\t", "|"]:
            for enc in ["utf-8", "gbk"]:
                try: return pd.read_csv(file_path, encoding=enc, sep=sep)
                except: continue
        raise ValueError("无法解析该 CSV 文件")
    else:
        try: return pd.read_excel(file_path, sheet_name=sheet_name, engine="openpyxl")
        except:
            try: return pd.read_excel(file_path, sheet_name=sheet_name, engine="xlrd")
            except: raise ValueError("无法解析该 Excel 文件")

def normalize_columns(df):
    renamed = {}
    for col in df.columns:
        c = str(col).strip()
        if c in COLUMN_MAP: renamed[col] = COLUMN_MAP[c]
        elif c.lower() in COLUMN_MAP: renamed[col] = COLUMN_MAP[c.lower()]
    return df.rename(columns=renamed)

def parse_as_orders(df):
    df = normalize_columns(df)
    if "order_id" not in df.columns or "driver_id" not in df.columns:
        return None, ["缺少 order_id/driver_id"]
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
    rows = df.where(df.notna(), None).to_dict(orient="records")
    return list(df.columns), rows

def load_any_file(file_path):
    """加载任意文件 — 支持多 Sheet Excel"""
    ext = Path(file_path).suffix.lower()
    if ext in (".xlsx", ".xls"):
        try:
            xl = pd.ExcelFile(file_path)
            sheets = xl.sheet_names
        except:
            sheets = ["Sheet1"]
    else:
        sheets = ["data"]

    datasets = {}
    all_orders = []
    warnings = []

    for sheet in sheets:
        try:
            df = read_file(file_path, sheet)
        except Exception as e:
            warnings.append(f"[{sheet}] {str(e)[:60]}")
            continue
        if df is None or df.empty:
            continue

        orders, errs = parse_as_orders(df)
        if orders and len(orders) > 0:
            all_orders.extend(orders)
            continue

        cols, rows = parse_as_dataset(df)
        datasets[sheet] = {"columns": cols, "rows": rows, "count": len(rows)}

    if all_orders:
        set_orders(all_orders)
        return {
            "type": "orders",
            "orders_loaded": len(all_orders),
            "drivers": len(set(o.driver_id for o in all_orders)),
            "sheets_used": len(sheets),
            "warnings": warnings[:5],
        }

    if datasets:
        set_datasets(datasets)
        all_cols = []
        for ds in datasets.values():
            all_cols.extend(ds["columns"])
        total = sum(d["count"] for d in datasets.values())
        first_key = list(datasets.keys())[0]
        return {
            "type": "dataset",
            "total_rows": total,
            "total_sheets": len(datasets),
            "sheets": {n: d["count"] for n, d in datasets.items()},
            "columns": list(dict.fromkeys(all_cols)),
            "warnings": warnings[:5],
            "preview": datasets[first_key]["rows"][:3],
        }

    raise ValueError("未能从文件中读取到任何数据")

def generate_template():
    return "order_id,driver_id,passenger_id,pickup_time,pickup_location,dropoff_location,distance_km,duration_min,fare,status,rating\nOR001,DRV001,PAS001,2024-01-01 08:30,朝阳区,海淀区,12.5,32,38.50,completed,4.8\n"