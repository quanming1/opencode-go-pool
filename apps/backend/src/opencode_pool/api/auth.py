"""Bearer 鉴权依赖（C3 FR4/FR6）。

策略：
- 鉴权未启用（无库内 key 且无 master key）→ 放行（兼容模式）；
- 启用后：Authorization: Bearer <有效 key> → 放行；否则 401。
挂载对象：/api/v1/* 转发端点与 /api/keys*、账号控制写端点。
"""

import json

from fastapi import Depends, HTTPException, Request

from opencode_pool.auth.gateway_key import KeyManager


def get_key_manager(request: Request) -> KeyManager:
    manager = request.app.state.key_manager
    if manager is None:
        raise HTTPException(status_code=500, detail="key_manager 未初始化")
    return manager


async def require_gateway_key(
    request: Request,
    manager: KeyManager = Depends(get_key_manager),
) -> KeyManager:
    """转发端点的 Bearer 校验依赖：鉴权未启用放行（兼容模式），启用后强制校验。"""
    if not manager.auth_enabled():
        return manager
    auth = request.headers.get("authorization", "")
    token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
    if not manager.verify(token):
        raise HTTPException(
            status_code=401,
            detail=json.dumps({"error": {"message": "invalid or missing gateway key"}}),
        )
    return manager


async def require_gateway_key_strict(
    request: Request,
    manager: KeyManager = Depends(get_key_manager),
) -> KeyManager:
    """keys/账号控制端点：即便鉴权未启用（无 key 可用）也要求携带
    master key 或任一有效 key；两者皆无则拒绝（防止裸奔状态下
    任何人生成 key 反向锁死网关）。

    例外：鉴权未启用且无 master key（完全裸奔）时放行——
    本机部署语义下等价于"管理员第一次配置"。
    """
    if not manager.auth_enabled() and not manager.master_key:
        return manager
    auth = request.headers.get("authorization", "")
    token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
    if not manager.verify(token):
        raise HTTPException(
            status_code=401,
            detail=json.dumps({"error": {"message": "invalid or missing gateway key"}}),
        )
    return manager
