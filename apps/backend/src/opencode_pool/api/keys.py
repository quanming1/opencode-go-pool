"""网关 key 管理 API（C3 FR3）。"""

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel

from opencode_pool.api._common import json_response
from opencode_pool.api.auth import require_gateway_key
from opencode_pool.auth.gateway_key import KeyManager

router = APIRouter(prefix="/api/keys", tags=["keys"])


class CreateKeyBody(BaseModel):
    label: str


@router.get("")
async def list_keys(
    manager: KeyManager = Depends(require_gateway_key),
) -> Response:
    """key 列表（元信息，无哈希）。"""
    return json_response({"keys": manager.list_keys()})


@router.post("")
async def create_key(
    body: CreateKeyBody,
    manager: KeyManager = Depends(require_gateway_key),
) -> Response:
    """生成新 key；明文 key 仅此一次返回。"""
    label = body.label.strip() or "unnamed"
    created = manager.create_key(label)
    if created is None:
        return json_response(
            {"error": {"message": "创建失败（存储不可用）"}}, status=500
        )
    return json_response(created, status=201)


@router.delete("/{key_id}")
async def revoke_key(
    key_id: int,
    manager: KeyManager = Depends(require_gateway_key),
) -> Response:
    """吊销 key（软删）。"""
    ok = manager.revoke_key(key_id)
    return json_response({"ok": ok})
