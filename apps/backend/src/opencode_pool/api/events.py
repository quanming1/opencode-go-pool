"""统一事件 API（C4）：GET /api/events（type 筛选 / limit）。

返回 {"events": [...]}，每项严格含 type/data/meta/time 四项（PRD-C4 §4）。
G7：查询移出事件循环（asyncio.to_thread），避免阻塞流式转发。
"""

import asyncio

from fastapi import APIRouter, Request, Response

from opencode_pool.api._common import get_state_service, json_response

router = APIRouter(prefix="/api", tags=["events"])


@router.get("/events")
async def events(
    request: Request,
    limit: int = 100,
    offset: int = 0,
    type: str = "",  # noqa: A002 - 与事件契约字段同名（?type=request,key_switch）
) -> Response:
    """统一事件列表（新→旧）；type 逗号分隔筛选，limit/offset 分页。"""
    recorder = get_state_service(request, "event_recorder")
    clamped = max(1, min(limit, 500))
    offset_clamped = max(0, offset)
    types = [t.strip() for t in (type or "").split(",") if t.strip()] or None
    data = await asyncio.to_thread(recorder.query, clamped, types, offset_clamped)
    total = await asyncio.to_thread(recorder.count, types)
    has_more = offset_clamped + len(data) < total
    return json_response(
        {"events": data, "offset": offset_clamped, "has_more": has_more}
    )