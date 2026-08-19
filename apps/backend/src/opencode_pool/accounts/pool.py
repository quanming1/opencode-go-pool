"""账号池：加载多账号、维护状态机、提供脱敏查询与选取。

状态机（B1 + B3 增强）：
    healthy --mark_down(reason, retry_after?)--> cooldown
        （cooldown_until = now + retry_after 或默认 TTL）
    cooldown --scan_cooldowns()/惰性_pick--> healthy（冷却到期自动恢复）
      --连续失败达阈值--> disabled（auto-disabled：需人工 enable 恢复）
    healthy/cooldown --disable(reason)--> disabled
    disabled --enable()--> 恢复（若原本 cooldown 且未到期，回到 cooldown）

线程安全：所有可变操作用 lock 保护。
切换历史：最近 N 条事件环形日志（B3 FR5）。
"""

import logging
import threading
from collections import deque
from collections.abc import Callable
from datetime import datetime, timedelta

from opencode_pool.accounts.models import Account, AccountStatus, mask_api_key

logger = logging.getLogger("opencode_pool.accounts.pool")

# 默认冷却 TTL：5 小时（对齐 OpenCode Go 5 小时窗口语义）
DEFAULT_COOLDOWN_SECONDS = 5 * 60 * 60
# 默认切换历史容量
DEFAULT_HISTORY_LIMIT = 20
# 默认连续失败自动禁用阈值
DEFAULT_MAX_CONSECUTIVE_FAILURES = 3


class AccountPool:
    """多账号池：加载 + 状态机 + 脱敏视图 + 选取 + 切换历史。"""

    def __init__(
        self,
        accounts: list[Account] | None = None,
        cooldown_seconds: int = DEFAULT_COOLDOWN_SECONDS,
        max_consecutive_failures: int = DEFAULT_MAX_CONSECUTIVE_FAILURES,
        history_limit: int = DEFAULT_HISTORY_LIMIT,
        now: Callable[[], datetime] = datetime.now,
    ) -> None:
        self._accounts: dict[str, Account] = {a.id: a for a in (accounts or [])}
        self._cooldown_seconds = cooldown_seconds
        self._max_consecutive_failures = max_consecutive_failures
        self._history: deque[dict] = deque(maxlen=history_limit)
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

        惰性处理 cooldown 到期：选中前先检查并恢复过期账号（B1）。
        B3：active 标记账号被使用（调用方在成功转发后调 record_success）。
        """
        with self._lock:
            self._recover_expired()
            for a in self._accounts.values():
                if a.status == AccountStatus.HEALTHY and a.enabled:
                    return a
            return None

    # ---- 状态流转 ----

    def mark_down(
        self,
        account_id: str,
        reason: str,
        retry_after: int | None = None,
        kind: str = "error",
    ) -> bool:
        """healthy -> cooldown（或连续失败达阈值 -> disabled）。

        Args:
            account_id: 目标账号。
            reason: 错误原因（不含密钥）。
            retry_after: 上游 Retry-After 秒数；有则 cooldown_until=now+retry_after，
                否则用默认 TTL（B3 FR2）。
            kind: 错误分类（quota/auth/server/...），入切换历史。

        Returns:
            False 当账号不存在或已 disabled。
        """
        with self._lock:
            a = self._accounts.get(account_id)
            if a is None:
                return False
            if not a.enabled:
                return False

            delay = retry_after if retry_after else self._cooldown_seconds
            a.status = AccountStatus.COOLDOWN
            a.cooldown_until = self._now() + timedelta(seconds=max(1, delay))
            a.last_error = reason
            a.error_count += 1
            a.consecutive_failures += 1

            # B3 FR3：连续失败达阈值 → 自动禁用（机器判定，人工 enable 恢复）
            if a.consecutive_failures >= self._max_consecutive_failures:
                a.status = AccountStatus.DISABLED
                a.enabled = False  # 禁用态不再参与 pick
                a.last_error = f"auto-disabled: consecutive failures ({a.consecutive_failures})"
                self._record_event(account_id, "auto_disable", a.last_error)
                logger.error(
                    "[accounts] %s 连续失败 %d 次（阈值 %d），自动禁用",
                    account_id,
                    a.consecutive_failures,
                    self._max_consecutive_failures,
                )
                return True

            self._record_event(account_id, kind, reason)
            logger.warning(
                "[accounts] %s 进入冷却（TTL=%ss），kind=%s 原因: %s",
                account_id,
                delay,
                kind,
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
            a.consecutive_failures = 0
            self._record_event(account_id, "clear", "manual clear")
            logger.info("[accounts] %s 清除状态 -> healthy", account_id)
            return True

    def record_success(self, account_id: str) -> None:
        """成功使用：重置连续失败计数（累计 error_count 保留）。"""
        with self._lock:
            a = self._accounts.get(account_id)
            if a is not None:
                a.consecutive_failures = 0

    def disable(self, account_id: str, reason: str) -> bool:
        """手动禁用（disabled 优先于其他状态）。"""
        with self._lock:
            a = self._accounts.get(account_id)
            if a is None:
                return False
            a.enabled = False
            a.status = AccountStatus.DISABLED
            a.last_error = reason
            self._record_event(account_id, "disable", reason)
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
                a.error_count = 0
                a.consecutive_failures = 0
            self._record_event(account_id, "enable", "manual enable")
            logger.info("[accounts] %s 已启用", account_id)
            return True

    # ---- B3：主动扫描与切换历史 ----

    def scan_cooldowns(self) -> int:
        """主动扫描冷却到期的账号并恢复 healthy，返回恢复个数（B3 FR1）。"""
        with self._lock:
            recovered = 0
            now = self._now()
            for a in self._accounts.values():
                if (
                    a.status == AccountStatus.COOLDOWN
                    and a.cooldown_until
                    and now >= a.cooldown_until
                ):
                    a.status = AccountStatus.HEALTHY
                    a.cooldown_until = None
                    a.last_error = None
                    a.error_count = 0
                    a.consecutive_failures = 0
                    self._record_event(a.id, "recover", "cooldown expired")
                    recovered += 1
            if recovered:
                logger.info("[accounts] 主动扫描恢复 %d 个账号", recovered)
            return recovered

    def switch_history(self, limit: int = 0) -> list[dict]:
        """切换历史（最近事件，新→旧）。"""
        with self._lock:
            items = list(self._history)
            items.reverse()
            if limit > 0:
                items = items[:limit]
            return items

    def _recover_expired(self) -> None:
        """pick 前惰性恢复（既有逻辑，scan_cooldowns 的辅助）。"""
        now = self._now()
        for a in self._accounts.values():
            if (
                a.status == AccountStatus.COOLDOWN
                and a.cooldown_until
                and now >= a.cooldown_until
            ):
                a.status = AccountStatus.HEALTHY
                a.cooldown_until = None
                a.last_error = None
                a.error_count = 0
                a.consecutive_failures = 0
                self._record_event(a.id, "recover", "cooldown expired (lazy)")

    def _record_event(self, account_id: str, kind: str, reason: str) -> None:
        """追加一条切换/状态事件到环形历史。"""
        self._history.append(
            {
                "ts": self._now().isoformat(),
                "account_id": account_id,
                "kind": kind,
                "reason": reason,
            }
        )

    # ---- 日志用脱敏 ----

    def describe_key(self, account_id: str) -> str:
        """用于日志的脱敏密钥（仅末 4 位）。"""
        a = self._accounts.get(account_id)
        if a is None:
            return "<unknown>"
        return mask_api_key(a.api_key)
