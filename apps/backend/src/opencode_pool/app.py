"""FastAPI 应用工厂与 /health 端点。"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from opencode_pool import __version__
from opencode_pool.accounts.loader import load_accounts
from opencode_pool.accounts.pool import AccountPool
from opencode_pool.api.accounts import router as accounts_router
from opencode_pool.api.keys import router as keys_router
from opencode_pool.api.usage import router as usage_router
from opencode_pool.auth.gateway_key import KeyManager
from opencode_pool.config import settings
from opencode_pool.proxy import router as proxy_router
from opencode_pool.proxy.forwarder import Forwarder
from opencode_pool.proxy.router import alias_router as proxy_alias_router
from opencode_pool.scheduler import run_pool_scanner
from opencode_pool.store.sqlite_store import AccountStore

logger = logging.getLogger("opencode_pool.app")


def create_app(config_path: str | None = None) -> FastAPI:
    """创建 FastAPI 应用（工厂模式，便于测试注入）。

    Args:
        config_path: 账号配置文件路径；None 时用默认 config/accounts.yaml，
            文件不存在则空账号池（可启动，见 B1 PRD AC6）。
    """
    pool, store = _build_pool(config_path)

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

    # C2：用量记录器（与账号池共用同一 SQLite store）
    from opencode_pool.usage.recorder import UsageRecorder

    recorder = UsageRecorder(store)
    app.state.usage_recorder = recorder

    # C3：网关 key 管理（本地单用户默认免鉴权；.env.keys 配 GATEWAY_AUTH=on 启用校验）
    key_manager = KeyManager(
        store,
        master_key=_load_master_key(),
        auth_required=_load_auth_flag(),
    )
    app.state.key_manager = key_manager

    # 代理转发器（B2：多账号外层 + 透明转发；C2：记录用量）
    app.state.forwarder = Forwarder(
        pool=pool,
        upstream_base_url=settings.upstream_base_url,
        timeout=settings.upstream_timeout,
        usage_recorder=recorder,
    )

    app.include_router(accounts_router)
    app.include_router(proxy_router)
    app.include_router(proxy_alias_router)
    app.include_router(usage_router)
    app.include_router(keys_router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        """健康检查：返回状态与版本号。"""
        return {"status": "ok", "version": __version__}

    return app


def _load_master_key() -> str:
    """从 .env.keys 读取 GATEWAY_MASTER_KEY（可选，C3 FR2）。"""
    from opencode_pool.accounts.loader import _parse_env_file

    return _parse_env_file(".env.keys").get("GATEWAY_MASTER_KEY", "").strip()


def _load_auth_flag() -> bool:
    """从 .env.keys 读取 GATEWAY_AUTH（on/off，默认 off=本地免鉴权）。"""
    from opencode_pool.accounts.loader import _parse_env_file

    raw = _parse_env_file(".env.keys").get("GATEWAY_AUTH", "off").strip().lower()
    return raw in ("on", "true", "1")


def _build_pool(config_path: str | None) -> tuple[AccountPool, AccountStore]:
    """构建账号池与共用 store：加载配置 + B3 参数 + B4 持久化 + 从 DB 恢复。

    Args:
        config_path: 账号配置文件路径；None 用默认。

    Returns:
        (pool, store) —— store 供 UsageRecorder 共用（C2）。
    """
    if config_path is None:
        config_path = "config/accounts.yaml"
    accounts = load_accounts(config_path)

    # B4：SQLite 持久化（DB 不可写时 store.available=False，池退化为纯内存）
    store = AccountStore(settings.db_path)
    pool = AccountPool(
        accounts=accounts,
        max_consecutive_failures=settings.max_consecutive_failures,
        store=store,
    )

    # 从 DB 恢复上次运行时状态（冷却/禁用/计数）
    restored = pool.restore_from_store()
    if restored:
        logger.info("[app] 从持久化恢复 %d 个账号状态", restored)
    elif store.available:
        logger.info("[app] 无历史状态可恢复（首次启动或空库）")
    else:
        logger.warning("[app] SQLite 持久化不可用，本次运行状态不会跨重启保留")

    return pool, store


app = create_app()
