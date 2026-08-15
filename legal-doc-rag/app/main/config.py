"""
app/main/config.py —— 应用配置模块

【作用与功能】
负责加载环境变量和应用的基本配置。
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# 设置环境变量：默认开启 transformers 离线模式（本地已下载模型，不联网）。
# 使用 setdefault 而非强制赋值，以便 Docker 等环境通过 TRANSFORMERS_OFFLINE=0
# 在首次启动时联网拉取本地 BGE-M3 模型。
os.environ.setdefault('TRANSFORMERS_OFFLINE', '1')
os.environ['HF_HUB_DISABLE_SYMLINKS_WARNING'] = '1'

# 加载环境变量
env_path = Path(__file__).resolve().parent.parent.parent / ".env"
if env_path.exists():
    load_dotenv(str(env_path))

# 获取配置
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000").split(",")

def setup_config():
    """
    应用配置装配函数。

    环境变量与 ALLOWED_ORIGINS 已在模块导入阶段完成加载，
    此处仅作为与 create_app 装配流程保持一致的接口占位，
    返回当前生效的跨域白名单列表。
    """
    return ALLOWED_ORIGINS
