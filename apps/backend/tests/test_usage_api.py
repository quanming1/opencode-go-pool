"""usage API 集成测试（C2）+ 转发接线。"""

import httpx

from opencode_pool.accounts.models import Account
from opencode_pool.accounts.pool import AccountPool
from opencode_pool.events.recorder import EventRecorder
from opencode_pool.proxy.forwarder import Forwarder
from opencode_pool.store.sqlite_store import AccountStore
from opencode_pool.usage.recorder import UsageRecorder


def _app(tmp_path):
    """构造带 usage recorder 的测试 app（复用 B2 测试模式）。"""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    store = AccountStore(str(tmp_path / "api.db"))
    pool = AccountPool(
        accounts=[Account(id="a1", name="A", api_key="sk-1111")], store=store
    )
    rec = UsageRecorder(store)
    events = EventRecorder(store)

    app = FastAPI()
    app.state.account_pool = pool
    app.state.usage_recorder = rec
    app.state.event_recorder = events
    # C3：空 KeyManager（鉴权未启用 → 转发放行）
    from opencode_pool.auth.gateway_key import KeyManager

    app.state.key_manager = KeyManager(store)

    transport = httpx.MockTransport(
        lambda req: httpx.Response(
            200,
            json={
                "output": [],
                "usage": {"prompt_tokens": 100, "completion_tokens": 40},
            },
        )
    )
    fwd = Forwarder(
        pool=pool,
        upstream_base_url="http://fake/v1",
        client=httpx.AsyncClient(transport=transport),
        usage_recorder=rec,
        event_recorder=events,
    )
    app.state.forwarder = fwd

    from opencode_pool.api.events import router as events_router
    from opencode_pool.api.usage import router as usage_router
    from opencode_pool.proxy.router import router as proxy_router

    app.include_router(usage_router)
    app.include_router(proxy_router)
    app.include_router(events_router)
    return TestClient(app), rec, store


def test_stats_endpoint_empty(tmp_path):
    client, _, store = _app(tmp_path)
    resp = client.get("/api/stats")
    assert resp.status_code == 200
    body = resp.json()
    assert body["totals"]["request_count"] == 0
    assert body["buckets"] == []
    store.close()


def test_stats_endpoint_after_request(tmp_path):
    """AC8：发一条转发请求后 /api/stats 请求数 +1。"""
    client, _, store = _app(tmp_path)
    client.post("/api/v1/responses", json={"input": "hi", "stream": False})
    body = client.get("/api/stats").json()
    assert body["totals"]["request_count"] >= 1
    assert body["per_account"][0]["account_id"] == "a1"
    assert body["per_account"][0]["prompt_tokens"] == 100
    assert body["per_account"][0]["completion_tokens"] == 40
    store.close()


def test_error_request_records_error_type(tmp_path):
    """转发失败（400）记录 kind=error + error_type=bad_request。"""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    store = AccountStore(str(tmp_path / "err.db"))
    pool = AccountPool(accounts=[Account(id="a1", name="A", api_key="sk-1111")], store=store)
    rec = UsageRecorder(store)

    app = FastAPI()
    app.state.account_pool = pool
    app.state.usage_recorder = rec
    from opencode_pool.auth.gateway_key import KeyManager

    app.state.key_manager = KeyManager(store)

    transport = httpx.MockTransport(
        lambda req: httpx.Response(400, json={"error": {"message": "bad model"}})
    )
    fwd = Forwarder(
        pool=pool,
        upstream_base_url="http://fake/v1",
        client=httpx.AsyncClient(transport=transport),
        usage_recorder=rec,
    )
    app.state.forwarder = fwd

    from opencode_pool.api.usage import router as usage_router
    from opencode_pool.proxy.router import router as proxy_router

    app.include_router(usage_router)
    app.include_router(proxy_router)
    client = TestClient(app)

    client.post("/api/v1/responses", json={"input": "hi", "stream": False})
    body = client.get("/api/stats").json()
    assert body["totals"]["error_count"] >= 1
    store.close()
