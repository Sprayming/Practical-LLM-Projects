# =+= NEW MODULE - Added 2026-07-15 by Codex =+=\n\n# 多租户隔离管理器
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
    """单个租户"""

    def __init__(self, tenant_id: str, name: str):
        self.tenant_id = tenant_id
        self.name = name
        self.namespace = f"tenant:{tenant_id}"
        self.created_at = None
        from datetime import datetime
        self.created_at = datetime.now()

    def collection_name(self, base: str = "knowledge") -> str:
        """租户隔离的 Collection 名"""
        return f"{self.namespace}:{base}"

    def redis_prefix(self) -> str:
        """租户隔离的 Redis Key 前缀"""
        return f"{self.namespace}:memory"

    def __repr__(self):
        return f"Tenant({self.tenant_id}, {self.name})"


class TenantManager:
    """租户管理器 - 创建/查询/隔离"""

    def __init__(self):
        self._tenants: Dict[str, Tenant] = {}
        self._default_tenant: Optional[Tenant] = None
        # 创建默认租户
        self._default_tenant = self.create_tenant("default")

    def create_tenant(self, name: str) -> Tenant:
        tenant_id = str(uuid.uuid4())[:8]
        tenant = Tenant(tenant_id, name)
        self._tenants[tenant_id] = tenant
        logger.info("Tenant created: {} ({})", name, tenant_id)
        return tenant

    def get_tenant(self, tenant_id: str) -> Optional[Tenant]:
        return self._tenants.get(tenant_id)

    def get_default(self) -> Tenant:
        return self._default_tenant

    def delete_tenant(self, tenant_id: str) -> bool:
        tenant = self._tenants.pop(tenant_id, None)
        if tenant:
            logger.info("Tenant deleted: {} ({})", tenant.name, tenant_id)
            return True
        return False

    def list_tenants(self) -> list[Tenant]:
        return list(self._tenants.values())


# 全局单例
_manager: Optional[TenantManager] = None


def get_tenant_manager() -> TenantManager:
    global _manager
    if _manager is None:
        _manager = TenantManager()
    return _manager