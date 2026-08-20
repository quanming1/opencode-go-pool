"""代理转发集成测试：非流式/流式/切换/脱敏。

用 httpx.MockTransport 注入 fake 上游序列，验证 Forwarder 行为。
"""

from collections.abc import Callable

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from opencode_pool.accounts.models import Account
from opencode_pool.accounts.pool import AccountPool
from opencode_pool.proxy.forwarder import Forwarder


def _handle_streaming(*events: str) -> httpx.Response:
    """构造 SSE 流式响应的完整 body（MockTransport 下以 bytes 透传）。

    注意：MockTransport 对预载 bytes 的 aiter_raw 会抛 StreamConsumed，
    这里用 ByteStream 包装，让 httpx 把 body 当作可迭代流提供。
    """
    return httpx.Response(
        200,
        stream=httpx.ByteStream("".join(events).encode("utf-8")),
        headers={"content-type": "text/event-stream"},
    )


def _app_with_forwarder(
    pool: AccountPool, handler: Callable[[httpx.Request], httpx.Response]
) -> tuple[FastAPI, TestClient]:
    app = FastAPI()
    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    forwarder = Forwarder(pool=pool, upstream_base_url="http://fake/v1", timeout=5, client=client)
    app.state.account_pool = pool
    app.state.forwarder = forwarder

    declare_routes(app)
    return app, TestClient(app)


def declare_routes(app: FastAPI) -> None:
    """把 proxy router 挂到测试 app。"""
    from opencode_pool.proxy.router import router

    app.include_router(router)


def _request_factory(stream: bool = False) -> dict:
    return {"model": "gpt-5.6-luna", "input": "hi", "stream": stream}


# ---- 非流式 ----

def test_non_stream_transparent_json():
    calls: list[dict] = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append({"url": str(req.url), "auth": req.headers.get("authorization")})
        return httpx.Response(
            200,
            json={
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": "pong"}],
                    }
                ]
            },
            headers={"content-type": "application/json"},
        )

    pool = AccountPool(accounts=[Account(id="a1", name="A", api_key="sk-1111")])
    app, client = _app_with_forwarder(pool, handler)

    resp = client.post("/api/v1/responses", json=_request_factory(stream=False))
    assert resp.status_code == 200
    assert resp.headers.get("x-pool-account") == "a1"
    assert resp.json()["output"][0]["content"][0]["text"] == "pong"
    # 认证头使用账号密钥，目标地址为 {base}/responses
    assert calls[0]["auth"] == "Bearer sk-1111"
    assert calls[0]["url"] == "http://fake/v1/responses"


def test_stream_transparent_sse_order():
    events = [
        'data: {"type":"response.output_text.delta","delta":"你"}\n\n',
        'data: {"type":"response.output_text.delta","delta":"好"}\n\n',
        'data: {"type":"response.completed"}\n\n',
    ]

    def handler(req: httpx.Request) -> httpx.Response:
        return _handle_streaming(*events)

    pool = AccountPool(accounts=[Account(id="a1", name="A", api_key="sk-1111")])
    app, client = _app_with_forwarder(pool, handler)

    with client.stream("POST", "/api/v1/responses", json=_request_factory(stream=True)) as resp:
        assert resp.status_code == 200
        assert resp.headers.get("content-type", "").startswith("text/event-stream")
        assert resp.headers.get("x-pool-account") == "a1"
        body = b"".join(resp.iter_raw())
    assert body == "".join(events).encode("utf-8")


# ---- 失败切换 ----

def test_quota_then_ok_switches_account_and_marks_down():
    # a1 上游 429，a2 上游 200；切到 a2，a1 变 cooldown
    accounting: dict[str, int] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        # 显示路径无账号 id → 用 authorization 区分
        auth = req.headers.get("authorization", "")
        if "sk-1111" in auth:
            accounting["a1"] = accounting.get("a1", 0) + 1
            return httpx.Response(429, json={"error": {"message": "rate limit"}})
        accounting.setdefault("a2", 0)
        return httpx.Response(200, json={"output": []})

    pool = AccountPool(
        accounts=[
            Account(id="a1", name="A", api_key="sk-1111"),
            Account(id="a2", name="B", api_key="sk-2222"),
        ]
    )
    app, client = _app_with_forwarder(pool, handler)

    resp = client.post("/api/v1/responses", json=_request_factory(stream=False))
    assert resp.status_code == 200
    assert resp.headers.get("x-pool-account") == "a2"
    assert accounting["a1"] == 1
    assert pool.account("a1").status.value == "cooldown"
    assert "quota" in (pool.account("a1").last_error or "")


def test_bad_request_does_not_mark_down():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": {"message": "bad model"}})

    pool = AccountPool(accounts=[Account(id="a1", name="A", api_key="sk-1111")])
    app, client = _app_with_forwarder(pool, handler)

    resp = client.post("/api/v1/responses", json=_request_factory(stream=False))
    assert resp.status_code == 400
    assert pool.account("a1").status.value == "healthy"
    assert pool.account("a1").error_count == 0


def test_no_healthy_account_returns_503():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"output": []})

    # 一个 disabled 账号 → pick_next 返回 None → 503
    pool = AccountPool(accounts=[Account(id="a1", name="A", api_key="sk-1111", enabled=False)])
    app, client = _app_with_forwarder(pool, handler)

    resp = client.post("/api/v1/responses", json=_request_factory(stream=False))
    assert resp.status_code == 503
    assert resp.json()["error"]["message"] == "no healthy account available"


def test_all_accounts_quota_returns_503():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": {"message": "rate limit"}})

    pool = AccountPool(
        accounts=[
            Account(id="a1", name="A", api_key="sk-1111"),
            Account(id="a2", name="B", api_key="sk-2222"),
        ]
    )
    app, client = _app_with_forwarder(pool, handler)

    resp = client.post("/api/v1/responses", json=_request_factory(stream=False))
    assert resp.status_code == 503
    assert pool.account("a1").status.value == "cooldown"
    assert pool.account("a2").status.value == "cooldown"


# ---- models ----

def test_list_models_aggregates_accounts():
    pool = AccountPool(
        accounts=[
            Account(id="a1", name="A", api_key="sk-1111", models=("gpt-5.6-luna", "gpt-5.6-terra")),
            Account(id="a2", name="B", api_key="sk-2222", models=("gpt-5.6-luna",)),
        ]
    )
    app, client = _app_with_forwarder(pool, lambda req: httpx.Response(200))

    resp = client.get("/api/v1/models")
    assert resp.status_code == 200
    ids = [m["id"] for m in resp.json()["data"]]
    assert ids == ["gpt-5.6-luna", "gpt-5.6-terra"]  # 去重保序


# ---- chat/completions 协议 ----

def test_chat_completions_forwards_to_chat_endpoint():
    """POST /api/v1/chat/completions 应转发到上游 /chat/completions（非 /responses）。"""
    urls: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        urls.append(str(req.url))
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-x",
                "object": "chat.completion",
                "choices": [
                    {"message": {"role": "assistant", "content": "好"}, "finish_reason": "stop"}
                ],
                "usage": {"prompt_tokens": 8, "completion_tokens": 3, "total_tokens": 11},
            },
        )

    pool = AccountPool(accounts=[Account(id="a1", name="A", api_key="sk-1111")])
    app, client = _app_with_forwarder(pool, handler)

    resp = client.post(
        "/api/v1/chat/completions",
        json={"model": "kimi-k2.5", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert resp.status_code == 200
    assert resp.json()["choices"][0]["message"]["content"] == "好"
    assert urls == ["http://fake/v1/chat/completions"]


def test_chat_completions_records_usage():
    """chat completions 成功响应的 usage（prompt/completion_tokens）计入统计。"""
    import tempfile
    from pathlib import Path

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from opencode_pool.proxy.forwarder import Forwarder
    from opencode_pool.proxy.router import router as proxy_router
    from opencode_pool.store.sqlite_store import AccountStore
    from opencode_pool.usage.recorder import UsageRecorder

    with tempfile.TemporaryDirectory() as td:
        store = AccountStore(str(Path(td) / "cc.db"))
        pool = AccountPool(
            accounts=[Account(id="a1", name="A", api_key="sk-1111")], store=store
        )
        rec = UsageRecorder(store)

        transport = httpx.MockTransport(
            lambda req: httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 8, "completion_tokens": 3},
                },
            )
        )
        app = FastAPI()
        app.state.account_pool = pool
        app.state.usage_recorder = rec
        app.state.forwarder = Forwarder(
            pool=pool,
            upstream_base_url="http://fake/v1",
            client=httpx.AsyncClient(transport=transport),
            usage_recorder=rec,
        )
        app.include_router(proxy_router)
        client = TestClient(app)

        client.post(
            "/api/v1/chat/completions",
            json={"model": "kimi-k2.5", "messages": [{"role": "user", "content": "hi"}]},
        )
        stats = store.aggregate_usage(hours=24)
        assert stats["totals"]["request_count"] == 1
        assert stats["totals"]["prompt_tokens"] == 8
        assert stats["totals"]["completion_tokens"] == 3
        store.close()
