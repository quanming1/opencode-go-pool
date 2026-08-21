"""api 包公共 helper（G6 FR2）。

把散落在各路由模块的「JSON 响应」「从 app.state 取服务」两类样板收敛到一处，
新增端点时不再复制同样的三五行业务无关代码。
"""

import json
from typing import Any

from fastapi import Request, Response


def json_response(data: dict[str, Any], status: int = 200) -> Response:
    """统一 JSON 响应（ensure_ascii=False 保留中文原文）。"""
    return Response(
        content=json.dumps(data, ensure_ascii=False),
        status_code=status,
        media_type="application/json",
    )


def get_state_service(request: Request, name: str) -> Any:
    """从 app.state 取服务；未初始化抛统一异常（避免调用方各自判空）。"""
    service = getattr(request.app.state, name, None)
    if service is None:
        raise RuntimeError(f"{name} 未初始化")
    return service
