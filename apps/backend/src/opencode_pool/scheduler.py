"""后台任务：主动冷却扫描（B3 FR1）。

周期性（默认 60s）调用 AccountPool.scan_cooldowns()，
让冷却到期的账号在无请求时也能自动恢复，不依赖下一次 pick 的惰性检查。
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable

from opencode_pool.accounts.pool import AccountPool

logger = logging.getLogger("opencode_pool.scheduler")

DEFAULT_SCAN_INTERVAL_SECONDS = 60


async def run_pool_scanner(
    pool: AccountPool,
    interval: float = DEFAULT_SCAN_INTERVAL_SECONDS,
    stop_event: asyncio.Event | None = None,
    hook: Callable[[AccountPool], Awaitable[None]] | None = None,
) -> None:
    """循环扫描冷却账号，直到 stop_event 置位（供 app 关闭时取消）。

    hook 用于测试注入（每次周期后可断言）；生产为 None。
    """
    logger.info("[scheduler] 冷却扫描启动（interval=%ss）", interval)
    try:
        while True:
            await asyncio.sleep(interval)
            pool.scan_cooldowns()
            if hook is not None:
                await hook(pool)
    except asyncio.CancelledError:
        logger.info("[scheduler] 冷却扫描停止")
        raise
