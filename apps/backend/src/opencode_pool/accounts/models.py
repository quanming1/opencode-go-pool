"""账号数据模型与状态枚举。"""

import enum
from dataclasses import dataclass, field
from datetime import datetime


class AccountStatus(enum.StrEnum):
    """账号运行状态。"""

    HEALTHY = "healthy"
    COOLDOWN = "cooldown"
    DISABLED = "disabled"


@dataclass
class Account:
    """单个上游账号。

    运行时状态（status 族字段）由 AccountPool 管理；配置字段（api_key 等）由 loader 填充。
    api_key 是真实密钥，只在内存持有，禁止写入日志或 API 响应。
    """

    id: str
    name: str
    api_key: str
    models: tuple[str, ...] = ()
    enabled: bool = True
    # 可选上游地址；空串 = 用全局 UPSTREAM_BASE_URL（见 Proxy Forwarder）
    base_url: str = ""

    # 运行时状态
    status: AccountStatus = AccountStatus.HEALTHY
    cooldown_until: datetime | None = None
    last_error: str | None = field(default=None)
    error_count: int = field(default=0)

    def public_view(self) -> dict:
        """对外渲染视图：不包含 api_key。"""
        return {
            "id": self.id,
            "name": self.name,
            "status": self.status.value,
            "cooldown_until": self.cooldown_until.isoformat() if self.cooldown_until else None,
            "last_error": self.last_error,
            "error_count": self.error_count,
            "enabled": self.enabled,
        }


def mask_api_key(key: str) -> str:
    """密钥打码：仅显示末 4 位，其余以 * 遮盖。"""
    if not key:
        return ""
    if len(key) <= 4:
        return "*" * len(key)
    return f"{'*' * (len(key) - 4)}{key[-4:]}"
