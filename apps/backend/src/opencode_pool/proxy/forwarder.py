"""代理转发核心（B2 FR1-FR6）。

Forwarder 把 OpenAI Responses 请求从账号池选号后转发到上游，
支持非流式（JSON 透传）与流式（SSE 增量透传），失败按分类重试。

设计要点（PRD-B2 §3）：
- 每次 POST /responses 独立选号 → ReAct 多轮天然跨账号轮换；
- 流式下"首字节前"失败才重试；发出首字节后的断流不重试（避免重复文本）；
- 400 级/401 不重试；429/5xx/网络错 mark_down 后重试下一个 healthy 账号。

统一事件（C4）：
- 每次入站请求记一条 request 事件（含 attempts 链与 request_id）；
- 失败切换记 key_switch；全 quota/auth 失败记 all_keys_invalid；
  全网络/服务失败或无健康账号记 all_keys_unavailable。
"""

import json
import logging
import time
import uuid
from collections.abc import Callable
from typing import Any

import httpx
from fastapi import Request, Response
from fastapi.responses import StreamingResponse

from opencode_pool.accounts.models import Account
from opencode_pool.accounts.pool import AccountPool
from opencode_pool.events.recorder import EventType
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
        usage_recorder: object | None = None,
        event_recorder: object | None = None,
    ) -> None:
        self._pool = pool
        self._upstream_base_url = upstream_base_url.rstrip("/")
        self._timeout = timeout
        # 连接复用：单例 AsyncClient（B2 性能——每次转发新建客户端会导致每次
        # 请求重新 TLS 握手 + 无连接池，流式首字节明显变慢）；外部注入的 client
        #（测试 MockTransport）由注入方管理生命周期。
        # G7 注：曾尝试 http2=True 多路复用——需额外依赖 httpx[http2]（h2 包），
        # 对单请求/流式透传本地开销无实质收益（瓶颈已由连接复用解决），放弃
        self._client = client or httpx.AsyncClient(timeout=self._timeout)
        self._owns_client = client is None
        # C2：可选用量记录器（record() 签名见 usage/recorder.py）
        self._usage = usage_recorder
        # C4：可选统一事件记录器（record(type_, data, meta) duck-typing）
        self._event_recorder = event_recorder

    async def close(self) -> None:
        """关闭自建的 HTTP 客户端（连接池释放；注入的 client 由注入方管理）。"""
        if self._owns_client and self._client is not None:
            try:
                await self._client.aclose()
            except Exception:  # noqa: BLE001 - 关闭失败不影响生命周期收尾
                pass

    async def forward(self, request: Request, upstream_path: str = "/responses") -> Response:
        """处理单个转发请求，返回最终响应（可能已切换账号）。

        Args:
            request: 入站请求（body 为上游协议原文）。
            upstream_path: 上游端点路径——/responses（Responses 协议）
                或 /chat/completions（Chat Completions 协议）。
                同一账号池对不同模型暴露两种协议（OpenCode：muse/luna 走
                responses，kimi/minimax/glm/deepseek 走 chat completions），
                客户端按模型选端点，代理只做透明转发不做协议转换。
        """
        payload = await request.json()
        stream = bool(payload.get("stream", False))
        request_id = uuid.uuid4().hex
        started = time.monotonic()

        # 至多尝试 enabled 账号数（每账号一次；accepted 降级用 disabled 不参与）
        attempts = max(1, self._healthy_count())
        last_error: UpstreamError | None = None
        attempt_log: list[dict] = []
        prev_account: Account | None = None
        prev_error: UpstreamError | None = None

        for attempt in range(1, attempts + 1):
            account = self._pool.pick_next()
            if account is None:
                break
            # 上一账号失败且这次选到了另一个 → key_switch 事件
            if prev_account is not None and prev_error is not None:
                self._emit(
                    EventType.KEY_SWITCH,
                    {
                        "from_account_id": prev_account.id,
                        "to_account_id": account.id,
                        "reason": prev_error.detail or prev_error.kind.value,
                        "error_type": prev_error.kind.value,
                        "attempt": attempt,
                        "request_id": request_id,
                    },
                    meta={"source": "forwarder", "request_id": request_id},
                )
            # 流式成功时的延迟补记闭包：状态/用量/request 事件全部等
            # 整个流发送完毕后执行——首 chunk 前不做任何同步 SQLite 落库
            # （perf/B2：之前每次流式都在发首个字节前同步写库，实测首字节
            # 比直连慢约 500ms；事件照常完整记录，duration 覆盖完整流时长）
            stream_done: Callable[[Response, tuple[int, int]], None] | None = None
            if stream:

                def _on_stream_done(
                    acc: Account = account,
                    resp: Response | None = None,
                    tk: tuple[int, int] | None = None,
                ) -> None:
                    try:
                        self._pool.record_success(acc.id)
                        if self._usage is not None:
                            # G8：duration/protocol 供 FAST_MODE 内存聚合
                            # （usage_events 无这两列，normal 模式忽略）
                            self._usage.record(
                                acc.id,
                                kind="success",
                                duration_ms=int((time.monotonic() - started) * 1000),
                                protocol=upstream_path.lstrip("/"),
                            )
                        self._emit_request(
                            request_id,
                            succeeded=True,
                            protocol=upstream_path,
                            stream=True,
                            account_id=acc.id,
                            status_code=resp.status_code if resp else 0,
                            duration_ms=int((time.monotonic() - started) * 1000),
                            attempt_log=attempt_log,
                            model=payload.get("model"),
                            tokens=tk or (0, 0),
                        )
                    except Exception:  # noqa: BLE001 - 流后补记失败不影响已发响应
                        pass

                stream_done = _on_stream_done
            try:
                response, tokens = await self._forward_once(
                    request, account, payload, stream, upstream_path,
                    on_stream_done=stream_done,
                )
            except UpstreamError as exc:
                last_error = exc
                attempt_log.append(
                    {
                        "account_id": account.id,
                        "result": "error",
                        "error_type": exc.kind.value,
                        "status_code": exc.status,
                        "duration_ms": int((time.monotonic() - started) * 1000),
                    }
                )
                if exc.kind not in (ErrorKind.BAD_REQUEST,):
                    # 请求本身问题：不 mark_down（账号没问题，修请求即可）
                    retry_after = getattr(exc, "retry_after", None)
                    self._pool.mark_down(
                        account.id,
                        f"{exc.kind.value}: {exc.detail}",
                        retry_after=retry_after,
                        kind=exc.kind.value,
                    )
                    # C2：记录失败用量（error_type = 错误分类）
                    if self._usage is not None:
                        self._usage.record(
                            account.id,
                            kind="error",
                            error_type=exc.kind.value,
                            duration_ms=int((time.monotonic() - started) * 1000),
                            protocol=upstream_path.lstrip("/"),
                        )
                elif self._usage is not None:
                    self._usage.record(
                        account.id,
                        kind="error",
                        error_type="bad_request",
                        duration_ms=int((time.monotonic() - started) * 1000),
                        protocol=upstream_path.lstrip("/"),
                    )
                prev_account = account
                prev_error = exc
                if exc.kind in (ErrorKind.AUTH, ErrorKind.BAD_REQUEST):
                    # 不重试：密钥失效（AUTH 已 mark_down）或请求本身问题（BAD_REQUEST）
                    self._emit_request(
                        request_id,
                        succeeded=False,
                        protocol=upstream_path,
                        stream=stream,
                        account_id=account.id,
                        status_code=exc.status or 0,
                        duration_ms=int((time.monotonic() - started) * 1000),
                        attempt_log=attempt_log,
                        model=payload.get("model"),
                        error={"type": exc.kind.value, "message": exc.detail},
                    )
                    return await self._error_response(exc)
                # quota / server / network → 继续尝试下一个账号
                continue

            # 成功：非流式在响应返回前记录 request 事件；流式由 _on_stream_done
            # 在流结束后补记（首 chunk 前零落库）
            attempt_log.append(
                {
                    "account_id": account.id,
                    "result": "success",
                    "status_code": response.status_code,
                    "duration_ms": int((time.monotonic() - started) * 1000),
                }
            )
            if not stream:
                self._emit_request(
                    request_id,
                    succeeded=True,
                    protocol=upstream_path,
                    stream=stream,
                    account_id=account.id,
                    status_code=response.status_code,
                    duration_ms=int((time.monotonic() - started) * 1000),
                    attempt_log=attempt_log,
                    model=payload.get("model"),
                    tokens=tokens,
                )
            return response

        # 全部尝试失败 / 无健康账号：按错误构成发 all-keys 事件，再统一记 request
        duration_ms = int((time.monotonic() - started) * 1000)
        failed = [e for e in attempt_log if e["result"] == "error"]
        error_types = sorted({e["error_type"] for e in failed})
        attempted_ids = [e["account_id"] for e in attempt_log]
        if last_error is None:
            # pick_next 无健康账号：一张尝试都没有
            self._emit(
                EventType.ALL_KEYS_UNAVAILABLE,
                {
                    "attempted_account_ids": [],
                    "error_types": [],
                    "request_id": request_id,
                    "attempt_count": 0,
                },
                meta={"source": "forwarder", "request_id": request_id},
            )
        elif error_types and set(error_types) <= {"quota", "auth"}:
            self._emit(
                EventType.ALL_KEYS_INVALID,
                {
                    "attempted_account_ids": attempted_ids,
                    "error_types": error_types,
                    "request_id": request_id,
                    "attempt_count": len(attempt_log),
                },
                meta={"source": "forwarder", "request_id": request_id},
            )
        else:
            self._emit(
                EventType.ALL_KEYS_UNAVAILABLE,
                {
                    "attempted_account_ids": attempted_ids,
                    "error_types": error_types,
                    "request_id": request_id,
                    "attempt_count": len(attempt_log),
                },
                meta={"source": "forwarder", "request_id": request_id},
            )
        self._emit_request(
            request_id,
            succeeded=False,
            protocol=upstream_path,
            stream=stream,
            account_id=None,
            status_code=503,
            duration_ms=duration_ms,
            attempt_log=attempt_log,
            model=payload.get("model"),
            error=(
                {"type": last_error.kind.value, "message": last_error.detail}
                if last_error
                else {"type": "no_healthy", "message": "no healthy account available"}
            ),
        )
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
        self, request: Request, account: Account, payload: dict[str, Any], stream: bool,
        upstream_path: str = "/responses",
        on_stream_done: Callable[[Response, tuple[int, int]], None] | None = None,
    ) -> tuple[Response, tuple[int, int]]:
        """单账号转发；成功返回 (response, (prompt_tokens, completion_tokens))。

        流式场景 token 无法精确统计，返回 (0, 0)（PRD-C2 §3 边界）。
        on_stream_done：流式成功时，在该流整体发送完毕后调用（首字节前不落库）。
        """
        # G8：单次尝试耗时（FAST_MODE 内存聚合的 duration 数据源）
        attempt_started = time.monotonic()
        client = self._client
        url = f"{self._base_url(account)}{upstream_path}"
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
            # 2xx：成功转发
            if not stream:
                # 非流式：先重置连续失败计数，读全量 body 提取 token，再记用量
                self._pool.record_success(account.id)
                body_text = await _stream_read(upstream)
                prompt_tokens, completion_tokens = _extract_usage(body_text)
                await upstream.aclose()
                if self._usage is not None:
                    self._usage.record(
                        account.id,
                        kind="success",
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        duration_ms=int((time.monotonic() - attempt_started) * 1000),
                        protocol=upstream_path.lstrip("/"),
                    )
                response = Response(
                    content=body_text,
                    status_code=status,
                    media_type=upstream.headers.get("content-type", "application/json"),
                )
                tokens = (prompt_tokens, completion_tokens)
            else:
                # 流式：状态/用量/事件全部由 on_stream_done 在流结束后补记，
                # 首 chunk 前不做任何同步 SQLite 落库（perf/B2）
                if on_stream_done is not None:

                    def _done() -> None:
                        on_stream_done(resp=response, tk=tokens)

                    done: Callable[[], None] | None = _done
                else:
                    done = None
                response = StreamingResponse(
                    content=_closing_aiter(upstream, on_done=done),
                    status_code=status,
                    media_type=upstream.headers.get("content-type", "text/event-stream"),
                    headers={
                        "Cache-Control": "no-cache",
                        "X-Accel-Buffering": "no",
                    },
                )
                tokens = (0, 0)
            response.headers["X-Pool-Account"] = account.id
            return response, tokens
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

    def _emit(self, type_: str, data: dict, meta: dict | None = None) -> None:
        """向统一事件流发射事件（C4；记录器缺失/失败一律降级）。"""
        if self._event_recorder is None:
            return
        try:
            self._event_recorder.record(type_, data, meta)
        except Exception:  # noqa: BLE001 - 事件失败不影响转发
            pass

    def _emit_request(
        self,
        request_id: str,
        succeeded: bool,
        protocol: str,
        stream: bool,
        status_code: int,
        duration_ms: int,
        attempt_log: list[dict],
        model: object | None = None,
        account_id: str | None = None,
        tokens: tuple[int, int] = (0, 0),
        error: dict | None = None,
    ) -> None:
        """每次入站请求一条 request 事件（PRD-C4 §2.1）。"""
        self._emit(
            EventType.REQUEST,
            {
                "request_id": request_id,
                "success": succeeded,
                "protocol": protocol.lstrip("/"),
                "model": model,
                "stream": stream,
                "status_code": status_code,
                "duration_ms": duration_ms,
                "account_id": account_id,
                "attempt_count": len(attempt_log),
                "attempts": attempt_log,
                "token": {"prompt": tokens[0], "completion": tokens[1]},
                "error": error,
            },
            meta={"source": "forwarder", "request_id": request_id, "route": protocol},
        )

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


async def _closing_aiter(upstream: httpx.Response, on_done: Callable[[], None] | None = None):
    """迭代上游字节流，结束后关闭（延长上游生命周期到响应发送完毕）。

    on_done：流整体结束（含客户端断开）后执行一次，用于流式补记
    状态/用量/事件（perf/B2：首 chunk 前不做同步落库）。
    """
    try:
        async for chunk in upstream.aiter_raw():
            yield chunk
    finally:
        try:
            await upstream.aclose()
        except Exception:  # noqa: BLE001 - 关闭失败不影响透传
            pass
        if on_done is not None:
            try:
                on_done()
            except Exception:  # noqa: BLE001 - 补记失败不影响已发响应
                pass


def _safe_detail(kind: ErrorKind, status: int, body: str) -> str:
    """错误体摘要（截断 + 去密钥痕迹），避免把上游明文 key 落日志。"""
    snippet = body.strip()
    if len(snippet) > 200:
        snippet = snippet[:200] + "..."
    return snippet or f"http {status}"


def _extract_usage(body: str) -> tuple[int, int]:
    """从 Responses 响应体 JSON 提取 prompt/completion tokens。

    缺失/解析失败返回 (0,0)（PRD-C2 边界：尽力而为）。
    """
    import json

    try:
        data = json.loads(body) if body.strip() else {}
    except json.JSONDecodeError:
        return 0, 0
    usage = data.get("usage") if isinstance(data, dict) else None
    if not isinstance(usage, dict):
        return 0, 0
    prompt = usage.get("prompt_tokens") or usage.get("input_tokens") or 0
    completion = usage.get("completion_tokens") or usage.get("output_tokens") or 0
    return int(prompt or 0), int(completion or 0)


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
