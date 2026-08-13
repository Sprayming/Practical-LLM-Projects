"""
app —— legal-doc-rag 法律文档 RAG 系统的顶层 Python 包（包标识文件）

【作用与功能】
作为整个 legal-doc-rag 系统的代码根包，使 `app` 目录成为可被 `import app...` 正常导入的包。
它本身不承载运行逻辑，而是声明包的边界，并作为各子模块（api、core、security、retrieval、
memory、worker、tenant 等）的统一命名空间入口。

【实现方式】
- 仅作为包标识文件存在，无运行时逻辑；真正的应用实例由 `app.main` 下的 `create_app()` 创建。
- 本文件统一导出核心构造入口：create_app、setup_config、setup_middleware、setup_routes、
  setup_static_files、setup_events，供应用启动装配使用。
- 注意：因导出会触发 `app.main` 的导入，任何 `import app` 都会连带创建并装配完整的 FastAPI
  实例；若只需某子模块（如配置），建议直接 `from app.core.config import X`，避免重初始化。

【整体作用】
legal-doc-rag 是一套完整的法律文档检索增强生成（RAG）系统，提供文档上传与处理、向量化
存储、智能检索、多轮对话、多租户隔离、异步任务、Webhook 通知与 A/B 测试等能力，
是 FastAPI 应用启动与所有业务模块相对导入的基础。
"""

__version__ = "1.0.0"
__author__ = "Legal Doc RAG Team"
__email__ = "team@legal-doc-rag.com"

# 导出主要接口
from .main.app import create_app
from .main.config import setup_config
from .main.middleware import setup_middleware
from .main.routes import setup_routes, setup_static_files
from .main.events import setup_events

__all__ = [
    "create_app",
    "setup_config",
    "setup_middleware",
    "setup_routes",
    "setup_static_files",
    "setup_events",
]
