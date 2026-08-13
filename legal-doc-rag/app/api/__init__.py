"""
app/api/__init__.py —— legal-doc-rag API 路由包初始化模块

【作用与功能】
本文件是 legal-doc-rag 项目 FastAPI 应用 API 层的包初始化文件。它将该目录标记为 Python
包，使上层应用(如 app/main/app.py 的 create_app)能够通过 `from app.api import xxx` 的方式统一导入各业务
路由模块(auth、chat、documents、admin、category、conversation、feedback、ab_testing、webhook)。

【主要组成】
- 本文件为包占位/初始化模块，自身不含运行时逻辑。
- 各具体路由实现分散在同级模块(auth.py、chat.py 等)中，每个模块各自定义并导出 `router` 实例。

【适用场景】
- 应用启动时由主程序导入本包下的各个 router 并挂载到 FastAPI 实例的对应前缀下。
- 新增 API 模块时，只需在本目录新建 `<name>.py` 并导出 `router`，即可被统一发现与注册。

【依赖关系】
- 上游调用方:app/main/ 包（app/main/app.py 的 create_app）等应用装配入口。
- 下游依赖:app.api 下的各业务路由模块(auth、chat、documents、admin、category、
  conversation、feedback、ab_testing、webhook)。
"""
"""
app.api —— API 路由模块

【作用与功能】
该模块包含所有 API 路由的定义：
- 认证路由
- 聊天路由
- 文档路由
- 反馈路由
- 管理员路由
- 分类路由
- 对话路由
- A/B 测试路由
- Webhook 路由
"""

from .auth import router as auth_router
from .chat import router as chat_router
from .documents import router as documents_router
from .feedback import router as feedback_router
from .admin import router as admin_router
from .category import router as category_router
from .conversation import router as conversation_router
from .ab_testing import router as ab_testing_router
from .webhook import router as webhook_router

__all__ = [
    "auth_router",
    "chat_router",
    "documents_router",
    "feedback_router",
    "admin_router",
    "category_router",
    "conversation_router",
    "ab_testing_router",
    "webhook_router",
]
