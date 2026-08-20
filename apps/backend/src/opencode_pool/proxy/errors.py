"""上游错误分类：把上游状态码/错误体归类为可处理的 ErrorKind。

分类规则（PRD-B2 FR6/FR7）：
    quota       → 429 / 含 rate limit / quota 关键词 → mark_down + 重试下一个
    auth        → 401 / 403 → mark_down + 不重试（密钥失效修完前重试无意义）
    bad_request → 400-499 其余 → 不 mark_down + 不重试（请求本身问题）
    server      → 5xx / 连接错误 → mark_down + 重试下一个
    ok          → 2xx
    network     → 连接层失败（httpx 网络异常）→ mark_down + 重试下一个
"""

import enum
import logging
from typing import Any

logger = logging.getLogger("opencode_pool.proxy.errors")

# 限流/额度关键词（大小写不敏感，命中即视为 quota）
_QUOTA_KEYWORDS = (
    "rate limit",
    "rate_limit",
    "ratelimit",
    "quota",
    "429",
    "usage limit",
    "usagelimit",
    "exhausted",
    "insufficient",
)


class ErrorKind(enum.StrEnum):
    OK = "ok"
    QUOTA = "quota"
    AUTH = "auth"
    BAD_REQUEST = "bad_request"
    SERVER = "server"
    NETWORK = "network"


class UpstreamError(Exception):
    """上游转发失败（含分类信息），供 Forwarder 决定重试策略。

    retry_after: 上游 Retry-After 头给出的重试秒数（可选，B3 FR8）。
    """

    def __init__(
        self,
        kind: ErrorKind,
        status: int | None = None,
        detail: str = "",
        retry_after: int | None = None,
    ) -> None:
        super().__init__(f"{kind.value}: {detail}")
        self.kind = kind
        self.status = status
        self.detail = detail
        self.retry_after = retry_after


def classify_upstream_status(status: int | None, body: str = "") -> ErrorKind:
    """按状态码与错误体分类。status=None 表示连接层无响应（网络错误）。"""
    if status is None:
        return ErrorKind.NETWORK
    if 200 <= status < 300:
        return ErrorKind.OK
    lower = (body or "").lower()
    if 200 <= status < 300:
        return ErrorKind.OK
    if status in (401, 403) and not any(kw in lower for kw in _QUOTA_KEYWORDS):
        return ErrorKind.AUTH
    if status == 429 or any(kw in lower for kw in _QUOTA_KEYWORDS):
        return ErrorKind.QUOTA
    if 400 <= status < 500:
        return ErrorKind.BAD_REQUEST
    return ErrorKind.SERVER


def json_error(status: int, message: str) -> dict[str, Any]:
    """构造 OpenAI 风格错误体（供非流式错误响应使用）。"""
    return {"error": {"message": message, "type": "proxy_error", "code": status}}
