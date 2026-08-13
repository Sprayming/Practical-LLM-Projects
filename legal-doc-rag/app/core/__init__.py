"""
app.core —— 核心配置与共享组件的包初始化模块(包标识文件)

【作用与功能】
该文件标志着 `app.core` 子包的存在。core 子包集中存放 legal-doc-rag 系统的
全局配置(config)与跨模块共享的基础设施(如请求限流器 limiter)，供上层
API 路由与安全中间件统一引用，避免配置与实例在多处重复创建。

【主要组成】
- `config`:全局配置模块，集中管理 LLM、嵌入模型、存储、Redis、JWT 等参数。
- `limiter`:全局请求限流器实例，配合 slowapi 对各 API 进行速率限制。

【适用场景】
- 场景1:各 API 路由通过 `from app.core import config` 读取运行参数。
- 场景2:应用入口(main.py)通过 `from app.core.limiter import limiter` 注册限流。

【依赖关系】
- 上游调用方:app.main 及 app.api 下的各业务路由。
- 下游依赖:标准库与第三方库(os、slowapi 等)，不反向依赖业务模块。
"""

# 集中暴露 core 子包的核心配置与限流器实例
# （注：task_store 位于 app.tasks、document_processor 不在 core，故不在此导出）
from .config import *
from .limiter import limiter

__all__ = ["limiter"]
