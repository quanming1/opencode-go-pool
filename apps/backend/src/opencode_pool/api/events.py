"""统一事件 API（C4）：GET /api/events（type 筛选 / limit）。

返回 {"events": [...]}，每项严格含 type/data/meta/time 四项（PRD-C4 §4）。
"""

import json

from fastapi import APIRouter, Request, Response

router = APIRouter(prefix="/api", tags=["events"])


def _get_recorder(request: Request):
    recorder = request.app.state.event_recorder
    if recorder is None:
        raise RuntimeError("event_recorder 未初始化")
    return recorder


@router.get("/events")
async def events(
    request: Request,
    limit: int = 100,
    type: str = "",  # noqa: A002 - 与事件契约字段同名（?type=request,key_switch）
) -> Response:
    """统一事件列表（新→旧）；type 逗号分隔筛选，limit 钳制 1..500。"""
    recorder = _get_recorder(request)
    clamped = max(1, min(limit, 500))
    types = [t.strip() for t in (type or "").split(",") if t.strip()] or None
    data = recorder.query(limit=clamped, types=types)
    return Response(
        content=json.dumps({"events": data}, ensure_ascii=False),
        status_code=200,
        media_type="application/json",
    )