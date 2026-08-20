"""代理 API 路由（B2/C3）：/api/v1/responses、/api/v1/chat/completions 与 /api/v1/models。

路由从 app.state 读取 Forwarder（由应用工厂注入，保证账号池共享）。

路径别名：标准 OpenAI SDK / LangChain 调用 /v1/*（无 /api 前缀），
因此同一组端点同时挂 /api/v1/* 和 /v1/* 两条路径。
"""

import json
import logging

from fastapi import APIRouter, Depends, Request, Response

from opencode_pool.api.auth import require_gateway_key

logger = logging.getLogger("opencode_pool.proxy.router")


def _get_forwarder(request: Request):
    """从 app.state 获取 Forwarder。"""
    forwarder = request.app.state.forwarder
    if forwarder is None:
        raise RuntimeError("forwarder 未初始化")
    return forwarder


async def _do_forward(request: Request, upstream_path: str) -> Response:
    """共用转发逻辑（responses / chat/completions 两种协议）。"""
    forwarder = _get_forwarder(request)
    try:
        return await forwarder.forward(request, upstream_path=upstream_path)
    except Exception as exc:  # noqa: BLE001 - 兜底避免 500 溅出内幕
        logger.warning("[proxy] %s 处理异常: %s", upstream_path, type(exc).__name__)
        return Response(
            content=json.dumps({"error": {"message": "proxy internal error"}}),
            status_code=502,
            media_type="application/json",
        )


async def _do_models(request: Request) -> Response:
    """共用模型清单。"""
    forwarder = _get_forwarder(request)
    data = await forwarder.list_models()
    return Response(
        content=json.dumps(data, ensure_ascii=False),
        status_code=200,
        media_type="application/json",
    )


# ---- 双路径（/api/v1/* 与 /v1/*）同一 handler 注册 ----
# 标准 OpenAI SDK / LangChain 调用 /v1/*（无 /api 前缀），监控台/文档用 /api/v1/*；
# 通过同一函数叠两个 APIRouter 的 route 装饰器，消除 alias handler 重复（G6 FR1）。

router = APIRouter(
    prefix="/api/v1",
    tags=["proxy"],
    dependencies=[Depends(require_gateway_key)],
)

alias_router = APIRouter(
    prefix="/v1",
    tags=["proxy-alias"],
    dependencies=[Depends(require_gateway_key)],
)


@router.post("/responses")
@alias_router.post("/responses")
async def responses(request: Request) -> Response:
    """OpenAI Responses 透明转发（流式/非流式）。"""
    return await _do_forward(request, "/responses")


@router.post("/chat/completions")
@alias_router.post("/chat/completions")
async def chat_completions(request: Request) -> Response:
    """OpenAI Chat Completions 透明转发（流式/非流式）。"""
    return await _do_forward(request, "/chat/completions")


@router.get("/models")
@alias_router.get("/models")
async def models(request: Request) -> Response:
    """返回账号池合并模型清单。"""
    return await _do_models(request)
