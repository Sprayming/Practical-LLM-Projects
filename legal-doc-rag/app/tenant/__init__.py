"""
tenant/__init__.py —— Legal-DOC-RAG 多租户子包入口

【作用与功能】
本文件为 app/tenant 多租户子包的包初始化与统一导出入口。该子包承载系统的
隔离与身份基础：auth 负责用户、租户与鉴权（含密码哈希、注册/登录、角色
管理、密码重置），tenant_manager 负责任户对象的创建与资源命名空间隔离
（Redis 前缀、向量库 Collection 等），category 与 conversation 则分别管理
文档分类与对话历史。本文件对外暴露最常用的函数与类，便于上层以
`from app.tenant import login, get_tenant_manager, Tenant` 的方式调用。

【主要组成】
- `auth`：用户/租户/明细、鉴权与密码管理（login/register/has_users 等）
- `tenant_manager`：租户对象与全局管理器（get_tenant_manager/Tenant）
- `category`：文档分类与文档归类（见 category.py）
- `conversation`：对话与消息历史（见 conversation.py）

【适用场景】
- 场景1：应用启动或路由层通过本包导入鉴权与租户管理函数
- 场景2：接口依赖注入中获取当前租户隔离的资源命名空间

【依赖关系】
- 上游调用方：app 主应用、路由/依赖注入层
- 下游依赖：app.tenant.auth、app.tenant.tenant_manager
"""
from app.tenant.auth import login, register, has_users
from app.tenant.tenant_manager import get_tenant_manager, Tenant