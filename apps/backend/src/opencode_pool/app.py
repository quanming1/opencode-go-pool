"""FastAPI 应用工厂与 /health 端点。"""

from fastapi import FastAPI

from opencode_pool import __version__


def create_app() -> FastAPI:
    """创建 FastAPI 应用（工厂模式，便于测试注入）。"""
    app = FastAPI(title="OpenCode Go Pool", version=__version__)

    @app.get("/health")
    async def health() -> dict[str, str]:
        """健康检查：返回状态与版本号。"""
        return {"status": "ok", "version": __version__}

    return app


app = create_app()
