import os

# 读取当前 loader.py 内容
root = "D:/git/rideops-ai/backend/app"

with open(root + "/data/loader.py", "r", encoding="utf-8") as f:
    content = f.read()

# 替换 load_orders_from_file 函数
old_func = """def load_orders_from_file(file_path):
    ext = Path(file_path).suffix.lower()
    if ext not in SUPPORTED_FORMATS:
        raise ValueError(f\"不支持的文件格式: {ext}\")

    if ext == \".csv\":
        df = pd.read_csv(file_path, encoding=\"utf-8\")
    else:
        df = pd.read_excel(file_path)

    if df.empty:
        raise ValueError(\"文件为空\")

    df = normalize_columns(df)
    required = [\"order_id\", \"driver_id\", \"pickup_time\", \"fare\"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f\"缺少必需列: {missing}。你的列名: {list(df.columns)}\")"""

new_func = """def read_file_to_df(file_path):
    \"\"\"读取 CSV/Excel 文件为 DataFrame\"\"\"
    ext = Path(file_path).suffix.lower()
    if ext not in SUPPORTED_FORMATS:
        raise ValueError(f\"不支持的文件格式: {ext}\")
    try:
        xl = pd.ExcelFile(file_path) if ext != \".csv\" else None
        sheet_names = xl.sheet_names if xl else [\"data\"]
    except:
        sheet_names = [\"data\"]
    if ext == \".csv\":
        df = pd.read_csv(file_path, encoding=\"utf-8\")
    else:
        # 默认读第一个有数据的 sheet
        df = pd.read_excel(file_path, sheet_name=0)
    if df.empty:
        raise ValueError(\"文件为空\")
    return df, sheet_names

def load_orders_from_file(file_path):
    df, _ = read_file_to_df(file_path)
    df = normalize_columns(df)
    # 宽松检查：只要有 order_id 或 driver_id 就算能加载
    found = [c for c in [\"order_id\", \"driver_id\", \"fare\"] if c in df.columns]
    if not found:
        # 完全不匹配 → 存储为通用数据集
        rows = df.where(df.notna(), None).to_dict(orient=\"records\")
        columns = list(df.columns)
        from app.data import set_dataset
        set_dataset(columns, rows)
        raise ValueError(f\"FILE_IS_DATASET:{len(rows)}行,{len(columns)}列\")
    required = [\"order_id\", \"driver_id\", \"pickup_time\", \"fare\"]"""

if old_func in content:
    content = content.replace(old_func, new_func)
    with open(root + "/data/loader.py", "w", encoding="utf-8") as f:
        f.write(content)
    print("loader.py 已更新")
else:
    print("未找到原始函数，请检查 loader.py 内容")
    print("查找的关键词: def load_orders_from_file")
