"""日志概览 API（D1 FR3/FR4）：GET /api/logs/overview。

读端点，与 /api/stats 同级开放（本地单用户模式）。
"""

import json
import logging

from fastapi import APIRouter, Request, Response

logger = logging.getLogger("opencode_pool.api.logs")

router = APIRouter(prefix="/api", tags=["logs"])


@router.get("/logs/overview")
async def logs_overview(request: Request) -> Response:
    """当前活跃 Key + 请求速率 + 剩余使用时长推测。"""
    service = request.app.state.logs_overview
    if service is None:
        raise RuntimeError("logs_overview 未初始化")
    quota = None
    quota_service = request.app.state.quota_service
    if quota_service is not None:
        try:
            quota = await quota_service.fetch(force=False)  # 复用 TTL 缓存
        except Exception:  # noqa: BLE001 - 额度取不到不影响概览其余部分
            logger.warning("[logs] 获取额度摘要失败（剩余推测降级）")
    data = service.overview(quota=quota)
    return Response(
        content=json.dumps(data, ensure_ascii=False),
        status_code=200,
        media_type="application/json",
    )
