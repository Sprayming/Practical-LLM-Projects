import os, sys

root = "D:/git/rideops-ai/backend/app"

# ===== 1. data/__init__.py — 多数据集存储 =====
code = r'''
from typing import List, Dict, Any
from app.models import Order

_datasets: Dict[str, Dict] = {}  # {sheet_name: {"columns": [...], "rows": [...]}}
_orders: List[Order] = []

def set_datasets(datasets: dict):
    global _datasets
    _datasets = datasets

def get_datasets() -> dict:
    return _datasets

def get_dataset_sheets() -> list:
    return list(_datasets.keys())

def get_dataset_info() -> dict:
    return {name: {"count": ds["count"], "columns": ds["columns"]} for name, ds in _datasets.items()}

def get_orders():
    return _orders

def set_orders(orders):
    global _orders
    _orders = orders

def clear():
    global _orders, _datasets
    _orders = []
    _datasets = {}
'''

with open(root + "/data/__init__.py", "w", encoding="utf-8") as f:
    f.write(code.strip())

# ===== 2. data/loader.py — 多 Sheet 加载 =====
with open(root + "/data/loader.py", "r", encoding="utf-8") as f:
    loader = f.read()

# 替换 load_any_file
old = """def load_any_file(file_path):
    \"\"\"加载任意文件，自动识别格式\"\"\"
    df = read_file(file_path)
    if df.empty:
        raise ValueError(\"文件为空，没有数据\")
    # 优先尝试解析为订单
    orders, errors = parse_as_orders(df)
    if orders is not None and len(orders) > 0:
        set_orders(orders)
        return {
            \"type\": \"orders\",
            \"orders_loaded\": len(orders),
            \"errors\": errors,
            \"drivers\": len(set(o.driver_id for o in orders)),
            \"preview\": [{\"order_id\": o.order_id, \"driver_id\": o.driver_id, \"fare\": o.fare, \"status\": o.status} for o in orders[:5]],
        }
    else:
        columns, rows = parse_as_dataset(df)
        return {
            \"type\": \"dataset\",
            \"rows\": len(rows),
            \"columns\": columns,
            \"errors\": errors,
            \"preview\": rows[:5],
        }"""

new = """def load_any_file(file_path):
    \"\"\"加载任意文件，多 Sheet 支持\"\"\"
    import pandas as pd
    ext = Path(file_path).suffix.lower()
    if ext in (\\".xlsx\\", \\".xls\\"):
        try:
            xl = pd.ExcelFile(file_path)
            sheets = xl.sheet_names
        except:
            sheets = [\\"Sheet1\\"]
    else:
        sheets = [\\"data\\"]

    datasets = {}
    all_orders = []
    total_errors = []
    type_used = \\"dataset\\"

    for sheet in sheets:
        try:
            df = read_file(file_path, sheet)
        except Exception as e:
            total_errors.append(f\\"{sheet}: {e}\\")
            continue

        if df.empty:
            continue

        orders, errs = parse_as_orders(df)
        if orders and len(orders) > 0:
            all_orders.extend(orders)
            type_used = \\"orders\\"
            continue

        columns, rows = parse_as_dataset(df)
        datasets[sheet] = {\\"columns\\": columns, \\"rows\\": rows, \\"count\\": len(rows)}

    # 如果有订单数据，优先返回订单
    if all_orders:
        from app.data import set_orders
        set_orders(all_orders)
        return {
            \\"type\\": \\"orders\\",
            \\"orders_loaded\\": len(all_orders),
            \\"drivers\\": len(set(o.driver_id for o in all_orders)),
            \\"sheets_loaded\\": len(sheets),
            \\"errors\\": total_errors[:5],
        }

    # 否则返回所有 Sheet 的数据集
    from app.data import set_datasets
    set_datasets(datasets)

    all_rows = sum(ds[\\"count\\"] for ds in datasets.values())
    all_cols = []
    for ds in datasets.values():
        all_cols.extend(ds[\\"columns\\"])

    return {
        \\"type\\": \\"dataset\\",
        \\"total_rows\\": all_rows,
        \\"total_sheets\\": len(sheets),
        \\"sheets\\": {name: ds[\\"count\\"] for name, ds in datasets.items()},
        \\"columns\\": list(dict.fromkeys(all_cols)),  # 去重
        \\"errors\\": total_errors[:5],
        \\"preview\\": next(iter(datasets.values()))[\\"rows\\"][:3] if datasets else [],
    }"""

# 修正 read_file 函数支持指定 sheet
old_read = """def read_file(file_path):
    ext = Path(file_path).suffix.lower()
    if ext not in SUPPORTED_FORMATS:
        raise ValueError(f\"不支持的文件格式: {ext}\")
    if ext == \\".csv\\":
        for enc in [\\"utf-8\\", \\"gbk\\", \\"gb2312\\", \\"latin-1\\"]:
            try:
                return pd.read_csv(file_path, encoding=enc)
            except Exception:
                continue
        for sep in [\\",\\", \\";\\", \\"\\\\t\\", \\"|\\"]:
            for enc in [\\"utf-8\\", \\"gbk\\"]:
                try:
                    return pd.read_csv(file_path, encoding=enc, sep=sep)
                except:
                    continue
        raise ValueError(\\"无法解析该 CSV 文件，请检查编码和分隔符\\")
    else:
        try:
            return pd.read_excel(file_path, sheet_name=0, engine=\\"openpyxl\\")
        except:
            try:
                return pd.read_excel(file_path, sheet_name=0, engine=\\"xlrd\\")
            except:
                raise ValueError(\\"无法解析该 Excel 文件，可能已损坏或加密\\")"""

new_read = """def read_file(file_path, sheet_name=0):
    ext = Path(file_path).suffix.lower()
    if ext not in SUPPORTED_FORMATS:
        raise ValueError(f\"不支持的文件格式: {ext}\")
    if ext == \\".csv\\":
        for enc in [\\"utf-8\\", \\"gbk\\", \\"gb2312\\", \\"latin-1\\"]:
            try:
                return pd.read_csv(file_path, encoding=enc)
            except Exception:
                continue
        for sep in [\\",\\", \\";\\", \\"\\\\t\\", \\"|\\"]:
            for enc in [\\"utf-8\\", \\"gbk\\"]:
                try:
                    return pd.read_csv(file_path, encoding=enc, sep=sep)
                except:
                    continue
        raise ValueError(\\"无法解析该 CSV 文件\\")
    else:
        try:
            return pd.read_excel(file_path, sheet_name=sheet_name, engine=\\"openpyxl\\")
        except:
            try:
                return pd.read_excel(file_path, sheet_name=sheet_name, engine=\\"xlrd\\")
            except:
                raise ValueError(\\"无法解析该 Excel 文件，可能已损坏或加密\\")"""

if old.strip() in loader:
    loader = loader.replace(old.strip(), new.strip())
    print("load_any_file 已更新")
else:
    print("load_any_file 替换失败，检查内容")

if old_read.strip() in loader:
    loader = loader.replace(old_read.strip(), new_read.strip())
    print("read_file 已更新（支持指定 sheet）")
else:
    print("read_file 替换失败，检查内容")

with open(root + "/data/loader.py", "w", encoding="utf-8") as f:
    f.write(loader)

# ===== 3. api/analysis.py — 更新 _build_context_data =====
with open(root + "/api/analysis.py", "r", encoding="utf-8") as f:
    analysis = f.read()

old_ctx = """def _build_context_data():
    \"\"\"构建 AI 问答的上下文\"\"\"
    orders = get_orders()
    if orders:
        from app.analysis.statistics import compute_kpi
        from app.analysis.trends import daily_trends
        from app.analysis.anomalies import detect_anomalies
        kpi = compute_kpi(orders)
        trends = daily_trends(orders)
        anomalies = detect_anomalies(orders, settings.anomaly_threshold)
        lines = [
            f\"订单数据：共{len(orders)}条，{kpi.get('active_drivers',0)}位司机\",
            f\"完成{kpi.get('completed_orders',0)}单，收入{kpi.get('total_revenue',0)}元\",
            f\"平均评分{kpi.get('avg_rating',0)}，高峰{kpi.get('peak_hour','')}\",
        ]
        if anomalies:
            for a in anomalies:
                lines.append(f\"异常：{a['date']} {a['metric']}\")
        return \"\\n\".join(lines)

    ds = get_dataset()
    if ds[\"count\"] > 0:
        return _format_dataset_context()
    return \"暂无数据，请先上传数据文件\""""

new_ctx = """def _build_context_data():
    \"\"\"构建 AI 问答的上下文（支持多 Sheet）\"\"\"
    orders = get_orders()
    if orders:
        from app.analysis.statistics import compute_kpi
        from app.analysis.trends import daily_trends
        from app.analysis.anomalies import detect_anomalies
        kpi = compute_kpi(orders)
        trends = daily_trends(orders)
        anomalies = detect_anomalies(orders, settings.anomaly_threshold)
        lines = [
            f\"订单数据：共{len(orders)}条，{kpi.get('active_drivers',0)}位司机\",
            f\"完成{kpi.get('completed_orders',0)}单，收入{kpi.get('total_revenue',0)}元\",
            f\"平均评分{kpi.get('avg_rating',0)}，高峰{kpi.get('peak_hour','')}\",
        ]
        if anomalies:
            for a in anomalies:
                lines.append(f\"异常：{a['date']} {a['metric']}\")
        return \"\\n\".join(lines)

    ds_info = get_dataset_info()
    if ds_info:
        lines = [f\"共 {len(ds_info)} 个数据表：\"]
        for name, info in ds_info.items():
            lines.append(f\"  - [{name}]: {info['count']}行, {len(info['columns'])}列 ({', '.join(info['columns'][:6])})\")
        return \"\\n\".join(lines)

    ds = get_dataset()
    if ds[\"count\"] > 0:
        return _format_dataset_context()
    return \"暂无数据，请先上传数据文件\""""

if old_ctx.strip() in analysis:
    analysis = analysis.replace(old_ctx.strip(), new_ctx.strip())
    print("analysis.py 已更新")
else:
    print("analysis.py 替换失败，检查内容")

with open(root + "/api/analysis.py", "w", encoding="utf-8") as f:
    f.write(analysis)

print("\\n所有文件已更新")
