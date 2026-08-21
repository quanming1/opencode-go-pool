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
from opencode_pool.events.recorder import EventRecorder
from opencode_pool.proxy import router as proxy_router
from opencode_pool.proxy.forwarder import Forwarder
from opencode_pool.proxy.router import alias_router as proxy_alias_router
from opencode_pool.scheduler import run_pool_scanner
from opencode_pool.store.sqlite_store import AccountStore
from opencode_pool.store.writer import SQLiteWriter

logger = logging.getLogger("opencode_pool.app")


def create_app(config_path: str | None = None) -> FastAPI:
    """创建 FastAPI 应用（工厂模式，便于测试注入）。

    Args:
        config_path: 账号配置文件路径；None 时用默认 config/accounts.yaml，
            文件不存在则空账号池（可启动，见 B1 PRD AC6）。
    """
    pool, store, event_recorder, writer = _build_pool(config_path)

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
            await app.state.quota_service.close()
            writer.flush()
            writer.close()
            # perf/B2：回收转发器自建的 HTTP 连接池（AsyncClient）
            await app.state.forwarder.close()
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            logger.info("[app] lifespan 结束，冷却扫描已停止")

    app = FastAPI(title="OpenCode Go Pool", version=__version__, lifespan=lifespan)
    app.state.account_pool = pool
    # C4：统一事件记录器（与账号池/用量/网关 key 共用同一 SQLite store）
    app.state.event_recorder = event_recorder

    # C2：用量记录器（与账号池共用同一 SQLite store）
    from opencode_pool.usage.recorder import UsageRecorder

    recorder = UsageRecorder(store, writer=writer)
    app.state.usage_recorder = recorder

    # C5：额度查询服务（官方 usage 接口 + TTL 缓存；失败降级不影响转发）
    from opencode_pool.quota.service import QuotaService

    app.state.quota_service = QuotaService(
        pool,
        cache_ttl=settings.quota_cache_ttl_seconds,
        timeout=settings.quota_timeout_seconds,
        upstream_base_url=settings.upstream_base_url,
    )

    # C3：网关 key 管理（本地单用户默认免鉴权；.env.keys 配 GATEWAY_AUTH=on 启用校验）
    key_manager = KeyManager(
        store,
        master_key=_load_master_key(),
        auth_required=_load_auth_flag(),
        event_recorder=event_recorder,
    )
    app.state.key_manager = key_manager

    # D1：日志概览（当前活跃 Key + 速率 + 剩余时长推测；复用 store 与事件记录器）
    from opencode_pool.logs.overview import LogsOverview

    app.state.logs_overview = LogsOverview(store, event_recorder)

    # 代理转发器（B2：多账号外层 + 透明转发；C2：记录用量；C4：记录统一事件）
    app.state.forwarder = Forwarder(
        pool=pool,
        upstream_base_url=settings.upstream_base_url,
        timeout=settings.upstream_timeout,
        usage_recorder=recorder,
        event_recorder=event_recorder,
    )

    app.include_router(accounts_router)
    app.include_router(proxy_router)
    app.include_router(proxy_alias_router)
    app.include_router(usage_router)
    app.include_router(keys_router)
    from opencode_pool.api.events import router as events_router
    from opencode_pool.api.quota import router as quota_router

    app.include_router(events_router)
    app.include_router(quota_router)
    from opencode_pool.api.logs import router as logs_router

    app.include_router(logs_router)

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


def _build_pool(
    config_path: str | None,
) -> tuple[AccountPool, AccountStore, EventRecorder, object]:
    """构建账号池 + 共用 store + 统一事件记录器（+ 异步落库队列）。

    Args:
        config_path: 账号配置文件路径；None 用默认。

    Returns:
        (pool, store, event_recorder, writer) —— store 供 UsageRecorder 共用（C2），
        event_recorder 注入账号池状态事件（C4），writer 为 G7 单写线程落库队列
        （event_recorder/UsageRecorder 共享，零阻塞热路径）。
    """
    if config_path is None:
        config_path = "config/accounts.yaml"
    accounts = load_accounts(config_path)

    # B4：SQLite 持久化（DB 不可写时 store.available=False，池退化为纯内存；
    # C4：构造函数内自动迁移旧 switch_history 表）
    store = AccountStore(settings.db_path)
    # G7：单写线程落库队列（转发与轮询热路径零同步 IO）
    writer = SQLiteWriter()
    event_recorder = EventRecorder(store, writer=writer)
    pool = AccountPool(
        accounts=accounts,
        max_consecutive_failures=settings.max_consecutive_failures,
        store=store,
        event_recorder=event_recorder,
    )

    # 从 DB 恢复上次运行时状态（冷却/禁用/计数）
    restored = pool.restore_from_store()
    if restored:
        logger.info("[app] 从持久化恢复 %d 个账号状态", restored)
    elif store.available:
        logger.info("[app] 无历史状态可恢复（首次启动或空库）")
    else:
        logger.warning("[app] SQLite 持久化不可用，本次运行状态不会跨重启保留")

    return pool, store, event_recorder, writer


app = create_app()
