"""
app.main —— 应用主模块

【作用与功能】
该模块包含 FastAPI 应用的核心组件：
- 应用创建和配置
- 中间件设置
- 路由注册
- 事件处理
- 静态文件服务
"""

from .app import create_app
from .config import setup_config
from .middleware import setup_middleware
from .routes import setup_routes, setup_static_files
from .events import setup_events

__all__ = [
    "create_app",
    "setup_config",
    "setup_middleware",
    "setup_routes",
    "setup_static_files",
    "setup_events",
]

# 供 uvicorn 以 `app.main:app` 形式直接加载的全局应用实例
# （docker-compose.yml / run.py / 各启动脚本均依赖此属性）
app = create_app()

# 允许以 `python -m app.main` 直接拉起 ASGI 服务（开发调试用）
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
