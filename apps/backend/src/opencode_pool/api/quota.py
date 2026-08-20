"""额度查询 API（C5 FR3）：GET /api/quota?refresh=0|1。

读端点，与 /api/stats 同级开放（本地单用户模式）；refresh=1 强制绕过缓存。
"""

import json

from fastapi import APIRouter, Request, Response

router = APIRouter(prefix="/api", tags=["quota"])


@router.get("/quota")
async def quota(request: Request, refresh: int = 0) -> Response:
    """账号额度（rolling/weekly/monthly 三窗口）+ 全池汇总。"""
    service = request.app.state.quota_service
    if service is None:
        raise RuntimeError("quota_service 未初始化")
    data = await service.fetch(force=bool(refresh))
    return Response(
        content=json.dumps(data, ensure_ascii=False),
        status_code=200,
        media_type="application/json",
    )