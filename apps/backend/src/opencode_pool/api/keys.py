"""网关 key 管理 API（C3 FR3）。"""

import json

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel

from opencode_pool.api.auth import require_gateway_key_strict
from opencode_pool.auth.gateway_key import KeyManager

router = APIRouter(prefix="/api/keys", tags=["keys"])


class CreateKeyBody(BaseModel):
    label: str


def _json_response(data: dict, status: int = 200) -> Response:
    return Response(
        content=json.dumps(data, ensure_ascii=False),
        status_code=status,
        media_type="application/json",
    )


@router.get("")
async def list_keys(
    manager: KeyManager = Depends(require_gateway_key_strict),
) -> Response:
    """key 列表（元信息，无哈希）。"""
    return _json_response({"keys": manager.list_keys()})


@router.post("")
async def create_key(
    body: CreateKeyBody,
    manager: KeyManager = Depends(require_gateway_key_strict),
) -> Response:
    """生成新 key；明文 key 仅此一次返回。"""
    label = body.label.strip() or "unnamed"
    created = manager.create_key(label)
    if created is None:
        return _json_response(
            {"error": {"message": "创建失败（存储不可用）"}}, status=500
        )
    return _json_response(created, status=201)


@router.delete("/{key_id}")
async def revoke_key(
    key_id: int,
    manager: KeyManager = Depends(require_gateway_key_strict),
) -> Response:
    """吊销 key（软删）。"""
    ok = manager.revoke_key(key_id)
    return _json_response({"ok": ok})
