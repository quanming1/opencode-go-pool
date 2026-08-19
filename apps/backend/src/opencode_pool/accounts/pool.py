"""账号池：加载多账号、维护状态机、提供脱敏查询与选取。

状态机（FR4）：
    healthy --mark_down(reason)--> cooldown（cooldown_until = now + TTL）
    cooldown --cooldown_expired()--> healthy（或下次 pick 时惰性判断）
    healthy/cooldown --disable(reason)--> disabled
    disabled --enable()--> 恢复（若原本 cooldown 且未到期，回到 cooldown）

线程安全：所有可变操作用 lock 保护；状态机逻辑可被多协程/多线程调用。
"""

import logging
import threading
from collections.abc import Callable
from datetime import datetime, timedelta

from opencode_pool.accounts.models import Account, AccountStatus, mask_api_key

logger = logging.getLogger("opencode_pool.accounts.pool")

# 默认冷却 TTL：5 小时（对齐 OpenCode Go 5 小时窗口语义）
DEFAULT_COOLDOWN_SECONDS = 5 * 60 * 60


class AccountPool:
    """多账号池：加载 + 状态机 + 脱敏视图 + 选取。"""

    def __init__(
        self,
        accounts: list[Account] | None = None,
        cooldown_seconds: int = DEFAULT_COOLDOWN_SECONDS,
        now: Callable[[], datetime] = datetime.now,
    ) -> None:
        self._accounts: dict[str, Account] = {a.id: a for a in (accounts or [])}
        self._cooldown_seconds = cooldown_seconds
        self._now = now
        self._lock = threading.Lock()

    # ---- 查询 ----

    def get_all(self) -> list[Account]:
        """返回全部账号（引用原对象；外部应只读）。"""
        with self._lock:
            return list(self._accounts.values())

    def public_views(self) -> list[dict]:
        """全部账号的脱敏视图（不含 api_key）。"""
        with self._lock:
            return [a.public_view() for a in self._accounts.values()]

    def account(self, account_id: str) -> Account | None:
        with self._lock:
            return self._accounts.get(account_id)

    def pick_next(self) -> Account | None:
        """返回第一个 healthy 且 enabled 的账号；无则 None。

        惰性处理 cooldown 到期：选中前先检查并恢复过期账号。
        """
        with self._lock:
            for a in self._accounts.values():
                self._maybe_recover(a)
            for a in self._accounts.values():
                if a.status == AccountStatus.HEALTHY and a.enabled:
                    return a
            return None

    # ---- 状态流转 ----

    def mark_down(self, account_id: str, reason: str) -> bool:
        """healthy -> cooldown。账号不存在或已 disabled 时返回 False。"""
        with self._lock:
            a = self._accounts.get(account_id)
            if a is None or not a.enabled:
                return False
            if a.status == AccountStatus.COOLDOWN:
                # 已在冷却：刷新错误与过期时间
                a.last_error = reason
                a.error_count += 1
                return True
            a.status = AccountStatus.COOLDOWN
            a.cooldown_until = self._now() + timedelta(seconds=self._cooldown_seconds)
            a.last_error = reason
            a.error_count += 1
            logger.warning(
                "[accounts] %s 进入冷却（TTL=%ss），原因: %s",
                account_id,
                self._cooldown_seconds,
                reason,
            )
            return True

    def clear_account(self, account_id: str) -> bool:
        """任意状态 -> healthy，清空运行时字段。disabled 账号不恢复 enabled。"""
        with self._lock:
            a = self._accounts.get(account_id)
            if a is None:
                return False
            a.status = AccountStatus.HEALTHY
            a.cooldown_until = None
            a.last_error = None
            a.error_count = 0
            logger.info("[accounts] %s 清除状态 -> healthy", account_id)
            return True

    def disable(self, account_id: str, reason: str) -> bool:
        """手动禁用（disabled 优先于其他状态）。"""
        with self._lock:
            a = self._accounts.get(account_id)
            if a is None:
                return False
            a.enabled = False
            a.status = AccountStatus.DISABLED
            a.last_error = reason
            logger.warning("[accounts] %s 已禁用: %s", account_id, reason)
            return True

    def enable(self, account_id: str) -> bool:
        """解除禁用。若此前在 cooldown 且未到期 → 回到 cooldown 等过期。"""
        with self._lock:
            a = self._accounts.get(account_id)
            if a is None:
                return False
            a.enabled = True
            if a.cooldown_until and a.cooldown_until > self._now():
                a.status = AccountStatus.COOLDOWN
            else:
                a.status = AccountStatus.HEALTHY
                a.cooldown_until = None
            logger.info("[accounts] %s 已启用", account_id)
            return True

    def _maybe_recover(self, a: Account) -> None:
        """cooldown 到期自动恢复 healthy（惰性，pick 前调用）。"""
        if (
            a.status == AccountStatus.COOLDOWN
            and a.cooldown_until
            and self._now() >= a.cooldown_until
        ):
            logger.info("[accounts] %s 冷却到期，恢复 healthy", a.id)
            a.status = AccountStatus.HEALTHY
            a.cooldown_until = None
            a.last_error = None
            a.error_count = 0

    # ---- 日志用脱敏 ----

    def describe_key(self, account_id: str) -> str:
        """用于日志的脱敏密钥（仅末 4 位）。"""
        a = self._accounts.get(account_id)
        if a is None:
            return "<unknown>"
        return mask_api_key(a.api_key)
