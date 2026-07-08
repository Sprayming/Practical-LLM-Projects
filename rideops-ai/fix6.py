import os

root = "D:/git/rideops-ai/backend/app"
path = root + "/data/loader.py"

with open(path, "r", encoding="utf-8") as f:
    content = f.read()

# 替换 read_file 为更鲁棒的版本
old = """def read_file(file_path):
    ext = Path(file_path).suffix.lower()
    if ext not in SUPPORTED_FORMATS:
        raise ValueError(f"不支持的文件格式: {ext}")
    if ext == \".csv\":
        return pd.read_csv(file_path, encoding=\"utf-8\")
    else:
        return pd.read_excel(file_path, sheet_name=0)"""

new = """def read_file(file_path):
    ext = Path(file_path).suffix.lower()
    if ext not in SUPPORTED_FORMATS:
        raise ValueError(f"不支持的文件格式: {ext}")
    if ext == \".csv\":
        # 自动检测编码和分隔符
        for enc in [\"utf-8\", \"gbk\", \"gb2312\", \"latin-1\"]:
            try:
                return pd.read_csv(file_path, encoding=enc)
            except (UnicodeDecodeError, UnicodeError):
                continue
            except pd.errors.ParserError:
                continue
        # 换分隔符再试
        for sep in [\",\", \";\", \"\\t\", \"|\"]:
            for enc in [\"utf-8\", \"gbk\"]:
                try:
                    return pd.read_csv(file_path, encoding=enc, sep=sep)
                except:
                    continue
        raise ValueError(\"无法解析该 CSV 文件，请检查编码和分隔符\")
    else:
        # Excel: 自动检测引擎
        try:
            return pd.read_excel(file_path, sheet_name=0, engine=\"openpyxl\")
        except:
            try:
                return pd.read_excel(file_path, sheet_name=0, engine=\"xlrd\")
            except:
                raise ValueError(\"无法解析该 Excel 文件，可能已损坏或加密\")"""

if old.strip() in content:
    content = content.replace(old.strip(), new.strip())
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("read_file 已更新")
else:
    print("匹配失败，检查当前 read_file 内容:")
    for line in content.split("\\n"):
        if "def read_file" in line:
            print(line)
