"""用量统计与切换历史 API（C2 FR3/FR4）。"""

import json
import logging

from fastapi import APIRouter, Request, Response

logger = logging.getLogger("opencode_pool.api.usage")

router = APIRouter(prefix="/api", tags=["usage"])


def _get_recorder(request: Request):
    recorder = request.app.state.usage_recorder
    if recorder is None:
        raise RuntimeError("usage_recorder 未初始化")
    return recorder


def _json_response(data: dict) -> Response:
    return Response(
        content=json.dumps(data, ensure_ascii=False),
        status_code=200,
        media_type="application/json",
    )


@router.get("/stats")
async def stats(request: Request, hours: int = 24) -> Response:
    """用量聚合（按小时桶）与各账号汇总。"""
    recorder = _get_recorder(request)
    clamped = max(1, min(hours, 168))  # 1h - 7d
    return _json_response(recorder.stats(hours=clamped))


@router.get("/switch-history")
async def switch_history(request: Request, limit: int = 50) -> Response:
    """切换事件历史（新→旧，附中文 kind_label）。"""
    recorder = _get_recorder(request)
    clamped = max(1, min(limit, 200))
    return _json_response({"events": recorder.switch_history(limit=clamped)})
