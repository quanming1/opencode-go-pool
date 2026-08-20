"""Bearer 鉴权依赖（C3 FR4/FR6；2026-08-20 用户决策改为本地免鉴权模式）。

策略（本地单用户语义）：
- 默认全放行——本机一个人用，鉴权是给"网关暴露给别人"准备的，防自己人纯添堵；
- 保留 GATEWAY_AUTH=on 开关：真要对外暴露时在 .env.keys 打开，恢复完整
  Bearer 校验（key 管理 + 转发端点），key 体系代码不删，随开关生效。
"""

import json

from fastapi import Depends, HTTPException, Request

from opencode_pool.auth.gateway_key import KeyManager


def get_key_manager(request: Request) -> KeyManager:
    manager = request.app.state.key_manager
    if manager is None:
        raise HTTPException(status_code=500, detail="key_manager 未初始化")
    return manager


def _extract_token(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    return auth[7:].strip() if auth.lower().startswith("bearer ") else ""


async def require_gateway_key(
    request: Request,
    manager: KeyManager = Depends(get_key_manager),
) -> KeyManager:
    """端点鉴权：GATEWAY_AUTH=on 时校验 Bearer，否则放行（本地模式）。

    keys/账号控制等管理端点在 C3 早期有独立 strict 分支，用户决策本地免鉴权后
    退化为与转发端点同一逻辑（G6 FR3 已合并，不再保留空壳函数）。
    """
    if not manager.auth_required:
        return manager
    if not manager.verify(_extract_token(request)):
        raise HTTPException(
            status_code=401,
            detail=json.dumps({"error": {"message": "invalid or missing gateway key"}}),
        )
    return manager
