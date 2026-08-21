"""用量统计 API（C2 FR3/FR4）：/api/stats。

C4：/api/switch-history 已删除，前端统一消费 /api/events（见 api/events.py）。
G7：聚合查询移出事件循环（asyncio.to_thread）+ 3s TTL 缓存（UsageRecorder 内，
监控台 10s 轮询命中缓存，零事件循环占用）。
"""

import asyncio
import logging

from fastapi import APIRouter, Request, Response

from opencode_pool.api._common import get_state_service, json_response

logger = logging.getLogger("opencode_pool.api.usage")

router = APIRouter(prefix="/api", tags=["usage"])


@router.get("/stats")
async def stats(request: Request, hours: int = 24) -> Response:
    """用量聚合（按小时桶）与各账号汇总。"""
    recorder = get_state_service(request, "usage_recorder")
    clamped = max(1, min(hours, 168))  # 1h - 7d
    data = await asyncio.to_thread(recorder.stats, clamped)
    return json_response(data)