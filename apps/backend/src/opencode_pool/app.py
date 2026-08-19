"""FastAPI 应用工厂与 /health 端点。"""

from fastapi import FastAPI

from opencode_pool import __version__
from opencode_pool.accounts.loader import load_accounts
from opencode_pool.accounts.pool import AccountPool
from opencode_pool.api.accounts import router as accounts_router


def create_app(config_path: str | None = None) -> FastAPI:
    """创建 FastAPI 应用（工厂模式，便于测试注入）。

    Args:
        config_path: 账号配置文件路径；None 时用默认 config/accounts.yaml，
            文件不存在则空账号池（可启动，见 B1 PRD AC6）。
    """
    app = FastAPI(title="OpenCode Go Pool", version=__version__)

    # 账号池（B1：内存态；B4 接持久化）
    if config_path is None:
        config_path = "config/accounts.yaml"
    accounts = load_accounts(config_path)
    app.state.account_pool = AccountPool(accounts=accounts)

    app.include_router(accounts_router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        """健康检查：返回状态与版本号。"""
        return {"status": "ok", "version": __version__}

    return app


app = create_app()
