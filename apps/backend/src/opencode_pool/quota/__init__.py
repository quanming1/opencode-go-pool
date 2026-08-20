"""额度查询模块（C5）：调 OpenCode 官方 usage 接口 + TTL 缓存。

统一事件（C4）不新增类型：额度查询为只读操作（PRD-C5 §1 非目标）。
"""

from opencode_pool.quota.service import QuotaService

__all__ = ["QuotaService"]