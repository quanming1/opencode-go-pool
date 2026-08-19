"""FastAPI 应用工厂与 /health 端点。"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from opencode_pool import __version__
from opencode_pool.accounts.loader import load_accounts
from opencode_pool.accounts.pool import AccountPool
from opencode_pool.api.accounts import router as accounts_router
from opencode_pool.config import settings
from opencode_pool.proxy import router as proxy_router
from opencode_pool.proxy.forwarder import Forwarder
from opencode_pool.scheduler import run_pool_scanner

logger = logging.getLogger("opencode_pool.app")


def create_app(config_path: str | None = None) -> FastAPI:
    """创建 FastAPI 应用（工厂模式，便于测试注入）。

    Args:
        config_path: 账号配置文件路径；None 时用默认 config/accounts.yaml，
            文件不存在则空账号池（可启动，见 B1 PRD AC6）。
    """
    pool = _build_pool(config_path)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # B3：后台冷却扫描（随应用启停）
        task = asyncio.create_task(
            run_pool_scanner(
                pool,
                interval=settings.pool_scan_interval_seconds,
            )
        )
        try:
            yield
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            logger.info("[app] lifespan 结束，冷却扫描已停止")

    app = FastAPI(title="OpenCode Go Pool", version=__version__, lifespan=lifespan)
    app.state.account_pool = pool

    # 代理转发器（B2：多账号外层 + 透明转发）
    app.state.forwarder = Forwarder(
        pool=pool,
        upstream_base_url=settings.upstream_base_url,
        timeout=settings.upstream_timeout,
    )

    app.include_router(accounts_router)
    app.include_router(proxy_router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        """健康检查：返回状态与版本号。"""
        return {"status": "ok", "version": __version__}

    return app


def _build_pool(config_path: str | None) -> AccountPool:
    """构建账号池（注入 B3 参数：扫描间隔 / 失败阈值）。"""
    if config_path is None:
        config_path = "config/accounts.yaml"
    accounts = load_accounts(config_path)
    return AccountPool(
        accounts=accounts,
        max_consecutive_failures=settings.max_consecutive_failures,
    )


app = create_app()
