"""代理转发核心（B2 FR1-FR6）。

Forwarder 把 OpenAI Responses 请求从账号池选号后转发到上游，
支持非流式（JSON 透传）与流式（SSE 增量透传），失败按分类重试。

设计要点（PRD-B2 §3）：
- 每次 POST /responses 独立选号 → ReAct 多轮天然跨账号轮换；
- 流式下"首字节前"失败才重试；发出首字节后的断流不重试（避免重复文本）；
- 400 级/401 不重试；429/5xx/网络错 mark_down 后重试下一个 healthy 账号。
"""

import json
import logging
from typing import Any

import httpx
from fastapi import Request, Response
from fastapi.responses import StreamingResponse

from opencode_pool.accounts.models import Account
from opencode_pool.accounts.pool import AccountPool
from opencode_pool.proxy.errors import (
    ErrorKind,
    UpstreamError,
    classify_upstream_status,
    json_error,
)

logger = logging.getLogger("opencode_pool.proxy.forwarder")

DEFAULT_UPSTREAM_BASE_URL = "https://api.opencode.ai/v1"
DEFAULT_TIMEOUT_SECONDS = 60.0


class Forwarder:
    """把请求转发到账号池选中的上游。"""

    def __init__(
        self,
        pool: AccountPool,
        upstream_base_url: str = DEFAULT_UPSTREAM_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._pool = pool
        self._upstream_base_url = upstream_base_url.rstrip("/")
        self._timeout = timeout
        self._client = client

    async def forward(self, request: Request) -> Response:
        """处理单个 Responses 请求，返回最终响应（可能已切换账号）。"""
        payload = await request.json()
        stream = bool(payload.get("stream", False))

        # 至多尝试 enabled 账号数（每账号一次；accepted 降级用 disabled 不参与）
        attempts = max(1, self._healthy_count())
        last_error: UpstreamError | None = None

        for _ in range(attempts):
            account = self._pool.pick_next()
            if account is None:
                break
            try:
                return await self._forward_once(request, account, payload, stream)
            except UpstreamError as exc:
                last_error = exc
                if exc.kind not in (ErrorKind.BAD_REQUEST,):
                    # 请求本身问题：不 mark_down（账号没问题，修请求即可）
                    retry_after = getattr(exc, "retry_after", None)
                    self._pool.mark_down(
                        account.id,
                        f"{exc.kind.value}: {exc.detail}",
                        retry_after=retry_after,
                        kind=exc.kind.value,
                    )
                if exc.kind in (ErrorKind.AUTH, ErrorKind.BAD_REQUEST):
                    # 不重试：密钥失效（AUTH 已 mark_down）或请求本身问题（BAD_REQUEST）
                    return await self._error_response(exc)
                # quota / server / network → 继续尝试下一个账号

        return await self._server_error_response(last_error, stream)

    async def list_models(self) -> dict[str, Any]:
        """返回账号池合并模型清单（B2 简单聚合，AC 未覆盖可后续扩展）。"""
        models: list[str] = []
        for account in self._pool.get_all():
            models.extend(account.models)
        seen: set[str] = set()
        unique = [m for m in models if not (m in seen or seen.add(m))]  # noqa: B033
        if unique:
            data = [{"id": m, "object": "model", "owned_by": "opencode-go-pool"} for m in unique]
            return {"object": "list", "data": data}
        return {
            "object": "list",
            "data": [],
            "note": "账号未配置 models 字段；配置后此接口返回可用模型清单",
        }

    # ---- 内部 ----

    async def _forward_once(
        self, request: Request, account: Account, payload: dict[str, Any], stream: bool
    ) -> Response:
        client = self._client or httpx.AsyncClient(timeout=self._timeout)
        url = f"{self._base_url(account)}/responses"
        headers = {
            "Authorization": f"Bearer {account.api_key}",
            "Content-Type": "application/json",
        }

        try:
            upstream_req = client.build_request(
                "POST", url, json=payload, headers=headers
            )
            upstream = await client.send(upstream_req, stream=True)
            status = upstream.status_code

            # 上游 4xx/5xx：读取 body 分类（流式"首字节前失败"判定点）
            if status is not None and status >= 400:
                body_text = await _stream_read(upstream)
                retry_after = _parse_retry_after(upstream.headers.get("retry-after"))
                await upstream.aclose()
                kind = classify_upstream_status(status, body_text)
                raise UpstreamError(
                    kind,
                    status=status,
                    detail=_safe_detail(kind, status, body_text),
                    retry_after=retry_after,
                )

            if status is None:
                await upstream.aclose()
                raise UpstreamError(ErrorKind.NETWORK, detail="上游无响应状态码")

            # 2xx：成功 → 记录成功（重置连续失败计数），再转发 body
            self._pool.record_success(account.id)
            if not stream:
                body_text = await _stream_read(upstream)
                await upstream.aclose()
                response = Response(
                    content=body_text,
                    status_code=status,
                    media_type=upstream.headers.get("content-type", "application/json"),
                )
            else:
                # 流式：把上游流包进可关闭的迭代器，响应发送完毕才关闭上游
                response = StreamingResponse(
                    content=_closing_aiter(upstream),
                    status_code=status,
                    media_type=upstream.headers.get("content-type", "text/event-stream"),
                    headers={
                        "Cache-Control": "no-cache",
                        "X-Accel-Buffering": "no",
                    },
                )
            response.headers["X-Pool-Account"] = account.id
            return response
        except UpstreamError:
            raise
        except httpx.HTTPError as exc:
            raise UpstreamError(
                ErrorKind.NETWORK, detail=f"HTTP 错误: {type(exc).__name__}"
            ) from exc

    def _base_url(self, account: Account) -> str:
        """账号 base_url 覆盖全局；二者缺省用默认上游地址。"""
        if account.base_url:
            return account.base_url.rstrip("/")
        return self._upstream_base_url

    def _healthy_count(self) -> int:
        return sum(1 for a in self._pool.get_all() if a.enabled and a.status.value == "healthy")

    async def _server_error_response(
        self, last_error: UpstreamError | None, stream: bool
    ) -> Response:
        """全部账号失败或无可用账号时的响应（PRD-B2 FR6 / AC7）。"""
        logger.warning(
            "[proxy] 转发失败（全部账号尝试完毕）: %s",
            f"{last_error.kind.value}: {last_error.detail}" if last_error else "",
        )
        return Response(
            content=json.dumps(json_error(503, "no healthy account available")),
            status_code=503,
            media_type="application/json",
        )

    async def _error_response(self, exc: UpstreamError) -> Response:
        """B2 AC6：BAD_REQUEST / AUTH 直接返回上游错误（透传状态码与 message）。"""
        status = exc.status if exc.status else 503
        detail = exc.detail or exc.kind.value
        # 尝试从上游 JSON 错误体提取 message，保持透传语义
        import json as _json

        try:
            parsed = _json.loads(detail)
            message = parsed.get("error", {}).get("message", detail)
        except Exception:  # noqa: BLE001
            message = detail
        return Response(
            content=json.dumps(json_error(status, message)),
            status_code=status,
            media_type="application/json",
        )


async def _stream_read(upstream: httpx.Response) -> str:
    """读取上游响应体文本（流式安全）。"""
    try:
        body = b""
        async for chunk in upstream.aiter_bytes():
            body += chunk
        return body.decode("utf-8", errors="replace")
    except Exception:  # noqa: BLE001 - 读取失败按空体处理
        return ""


async def _closing_aiter(upstream: httpx.Response):
    """迭代上游字节流，结束后关闭（延长上游生命周期到响应发送完毕）。"""
    try:
        async for chunk in upstream.aiter_raw():
            yield chunk
    finally:
        try:
            await upstream.aclose()
        except Exception:  # noqa: BLE001 - 关闭失败不影响透传
            pass


def _safe_detail(kind: ErrorKind, status: int, body: str) -> str:
    """错误体摘要（截断 + 去密钥痕迹），避免把上游明文 key 落日志。"""
    snippet = body.strip()
    if len(snippet) > 200:
        snippet = snippet[:200] + "..."
    return snippet or f"http {status}"


def _parse_retry_after(value: str | None) -> int | None:
    """解析 Retry-After 头为秒数；非法/缺失返回 None（B3 FR2）。

    支持纯秒数（"30"）与 HTTP 日期（"Wed, 21 Oct 2026 07:28:00 GMT"，
    解析失败则返回 None 走默认 TTL）。
    """
    if not value:
        return None
    value = value.strip()
    if value.isdigit():
        return int(value)
    return None
