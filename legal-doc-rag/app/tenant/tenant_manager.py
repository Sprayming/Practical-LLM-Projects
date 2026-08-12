"""
tenant_manager.py —— Legal-DOC-RAG 多租户管理器

【作用与功能】
本模块定义「租户（Tenant）」抽象与全局租户管理器，是系统多租户隔离的基石。
每个租户拥有独立的命名空间（`tenant:<id>`），进而派生出隔离的 Redis Key
前缀、向量库 Collection、记忆系统与文档索引，保证不同租户的数据互不干扰。
模块启动即创建默认租户，并通过 `get_tenant_manager()` 暴露全局单例。

【主要组成】
- `Tenant`：租户对象，提供 collection_name / redis_prefix 等隔离命名
- `TenantManager`：租户的创建、查询、删除与默认租户管理
- `get_tenant_manager()`：获取全局单例管理器

【适用场景】
- 场景1：应用启动时获取单例，初始化默认租户
- 场景2：业务层按 tenant_id 取得隔离的资源命名空间（向量库/缓存）

【依赖关系】
- 上游调用方：app 启动流程、向量库/记忆/缓存初始化
- 下游依赖：标准库 uuid、loguru
"""
#
# 每个租户拥有隔离的：
#   - 命名空间（Redis Key 前缀、ChromaDB Collection）
#   - 向量库实例
#   - 记忆系统实例
#   - 文档索引
import uuid
from typing import Optional, Dict
from loguru import logger


class Tenant:
    """单个租户。

    封装租户标识、名称与命名空间（`tenant:<id>`），并据此派生隔离的资源名
    （向量库 Collection、Redis Key 前缀），是数据隔离的边界单位。
    """

    def __init__(self, tenant_id: str, name: str):
        """初始化租户对象。

        参数:
            tenant_id (str): 租户唯一标识
            name (str): 租户名称（用于展示/日志）
        """
        self.tenant_id = tenant_id
        self.name = name
        self.namespace = f"tenant:{tenant_id}"
        self.created_at = None  # 占位，随后立即赋值
        from datetime import datetime
        self.created_at = datetime.now()

    def collection_name(self, base: str = "knowledge") -> str:
        """返回该租户隔离的向量库 Collection 名称。

        在命名空间上拼接业务基名（默认 knowledge），确保不同租户落到
        各自的 Collection。

        参数:
            base (str): 业务基名，默认 "knowledge"

        返回:
            str: 形如 `tenant:<id>:knowledge` 的 Collection 名
        """
        return f"{self.namespace}:{base}"

    def redis_prefix(self) -> str:
        """返回该租户隔离的 Redis Key 前缀。

        基于命名空间派生记忆系统的 Redis 前缀，避免跨租户键冲突。

        参数:
            无

        返回:
            str: 形如 `tenant:<id>:memory` 的 Redis 前缀
        """
        return f"{self.namespace}:memory"

    def __repr__(self):
        """返回便于调试的租户描述字符串。"""
        return f"Tenant({self.tenant_id}, {self.name})"


class TenantManager:
    """租户管理器 —— 负责租户的创建、查询与隔离。

    以字典维护内存中的租户对象，并在构造时创建默认租户，供未显式指定租户
    的场景使用。
    """

    def __init__(self):
        """初始化管理器并创建默认租户。"""
        self._tenants: Dict[str, Tenant] = {}
        self._default_tenant: Optional[Tenant] = None
        # 创建默认租户，作为无显式租户时的兜底
        self._default_tenant = self.create_tenant("default")

    def create_tenant(self, name: str) -> Tenant:
        """创建并登记一个新租户。

        生成 8 字符租户 ID，构造 `Tenant` 对象并存入内存字典，记录日志后返回。

        参数:
            name (str): 租户名称

        返回:
            Tenant: 新创建的租户对象

        异常:
            无
        适用场景:
            - 需要为新的隔离上下文建立租户时
        """
        tenant_id = str(uuid.uuid4())[:8]
        tenant = Tenant(tenant_id, name)
        self._tenants[tenant_id] = tenant
        logger.info("Tenant created: {} ({})", name, tenant_id)
        return tenant

    def get_tenant(self, tenant_id: str) -> Optional[Tenant]:
        """按 tenant_id 查询租户。

        参数:
            tenant_id (str): 租户标识

        返回:
            Optional[Tenant]: 命中的租户对象，或 None

        异常:
            无
        """
        return self._tenants.get(tenant_id)

    def get_default(self) -> Tenant:
        """返回默认租户。

        参数:
            无

        返回:
            Tenant: 默认租户对象

        异常:
            无
        适用场景:
            - 未指定租户时复用默认隔离命名空间
        """
        return self._default_tenant

    def delete_tenant(self, tenant_id: str) -> bool:
        """删除指定租户（仅内存态）。

        从字典中移除对应租户对象；移除成功返回 True，否则 False。

        参数:
            tenant_id (str): 待删除租户标识

        返回:
            bool: 是否成功删除

        异常:
            无
        适用场景:
            - 清理不再使用的租户（注意：此删除不触碰持久化数据）
        """
        tenant = self._tenants.pop(tenant_id, None)
        if tenant:
            logger.info("Tenant deleted: {} ({})", tenant.name, tenant_id)
            return True
        return False

    def list_tenants(self) -> list[Tenant]:
        """列出当前所有租户。

        参数:
            无

        返回:
            list[Tenant]: 租户对象列表

        异常:
            无
        """
        return list(self._tenants.values())


# 全局单例
_manager: Optional[TenantManager] = None


def get_tenant_manager() -> TenantManager:
    """获取全局单例租户管理器（懒初始化）。

    首次调用时创建 `TenantManager`（内含默认租户），之后复用同一实例，
    保证全应用共享同一套租户注册。

    参数:
        无

    返回:
        TenantManager: 全局唯一的管理器实例

    异常:
        无
    适用场景:
        - 应用启动与各处需要隔离资源命名空间时统一获取实例
    """
    global _manager
    if _manager is None:
        _manager = TenantManager()
    return _manager