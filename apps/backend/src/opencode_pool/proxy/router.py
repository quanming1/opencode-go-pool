"""代理 API 路由（B2）：/api/v1/responses 与 /api/v1/models。

路由从 app.state 读取 Forwarder（由应用工厂注入，保证账号池共享）。
"""

import json
import logging

from fastapi import APIRouter, Request, Response

logger = logging.getLogger("opencode_pool.proxy.router")

router = APIRouter(prefix="/api/v1", tags=["proxy"])


def _get_forwarder(request: Request):
    """从 app.state 获取 Forwarder。"""
    forwarder = request.app.state.forwarder
    if forwarder is None:
        raise RuntimeError("forwarder 未初始化")
    return forwarder


@router.post("/responses")
async def responses(request: Request) -> Response:
    """OpenAI Responses 透明转发（流式/非流式）。"""
    forwarder = _get_forwarder(request)
    try:
        return await forwarder.forward(request)
    except Exception as exc:  # noqa: BLE001 - 兜底避免 500 溅出内幕
        logger.warning("[proxy] responses 处理异常: %s", type(exc).__name__)
        return Response(
            content=json.dumps({"error": {"message": "proxy internal error"}}),
            status_code=502,
            media_type="application/json",
        )


@router.post("/chat/completions")
async def chat_completions(request: Request) -> Response:
    """OpenAI Chat Completions 透明转发（流式/非流式）。

    与 /responses 共用账号池与切换逻辑，仅上游端点不同
    （OpenCode 的 kimi/minimax/glm/deepseek 等模型走此协议）。
    """
    forwarder = _get_forwarder(request)
    try:
        return await forwarder.forward(request, upstream_path="/chat/completions")
    except Exception as exc:  # noqa: BLE001 - 兜底避免 500 溅出内幕
        logger.warning("[proxy] chat/completions 处理异常: %s", type(exc).__name__)
        return Response(
            content=json.dumps({"error": {"message": "proxy internal error"}}),
            status_code=502,
            media_type="application/json",
        )


@router.get("/models")
async def models(request: Request) -> Response:
    """返回账号池合并模型清单。"""
    forwarder = _get_forwarder(request)
    data = await forwarder.list_models()
    return Response(
        content=json.dumps(data, ensure_ascii=False),
        status_code=200,
        media_type="application/json",
    )
