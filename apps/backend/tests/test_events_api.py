"""统一事件 API 与转发链路事件（C4）：AC3/AC5/AC6。

用 httpx.MockTransport 注入 fake 上游，验证成功/失败/切换/全失效
各路径产生的事件类型与内容，以及 GET /api/events 的严格结构。
"""

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from opencode_pool.accounts.models import Account
from opencode_pool.accounts.pool import AccountPool
from opencode_pool.auth.gateway_key import KeyManager
from opencode_pool.events.recorder import EventRecorder
from opencode_pool.proxy.forwarder import Forwarder
from opencode_pool.store.sqlite_store import AccountStore


def _app(tmp_path, handler, accounts=None, event_limit=5000):
    """带统一事件记录器的测试 app：两个账号 + fake 上游 + /api/events。"""
    store = AccountStore(str(tmp_path / "ev.db"), event_limit=event_limit)
    events = EventRecorder(store)
    pool = AccountPool(
        accounts=accounts
        or [
            Account(id="a1", name="A1", api_key="sk-1111"),
            Account(id="a2", name="A2", api_key="sk-2222"),
        ],
        store=store,
        event_recorder=events,
    )

    app = FastAPI()
    app.state.account_pool = pool
    app.state.event_recorder = events
    app.state.key_manager = KeyManager(store, event_recorder=events)
    app.state.forwarder = Forwarder(
        pool=pool,
        upstream_base_url="http://fake/v1",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        event_recorder=events,
    )

    from opencode_pool.api.events import router as events_router
    from opencode_pool.api.keys import router as keys_router
    from opencode_pool.proxy.router import router as proxy_router

    app.include_router(events_router)
    app.include_router(proxy_router)
    app.include_router(keys_router)
    return TestClient(app), store


def _request(stream: bool = False) -> dict:
    return {"model": "gpt-5.6-luna", "input": "hi", "stream": stream}


def _ok_handler(req: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "output": [],
            "usage": {"prompt_tokens": 7, "completion_tokens": 3},
        },
    )


# ---- API 契约 ----

def test_events_endpoint_empty(tmp_path):
    client, store = _app(tmp_path, _ok_handler)
    resp = client.get("/api/events")
    assert resp.status_code == 200
    assert resp.json() == {"events": []}
    store.close()


def test_events_endpoint_strict_shape_after_request(tmp_path):
    """转发成功后 /api/events 返回严格 type/data/meta/time（AC6）。"""
    client, store = _app(tmp_path, _ok_handler)
    client.post("/api/v1/responses", json=_request())

    body = client.get("/api/events").json()
    assert len(body["events"]) == 1
    ev = body["events"][0]
    assert set(ev.keys()) == {"type", "data", "meta", "time"}
    assert ev["type"] == "request"
    assert ev["data"]["success"] is True
    store.close()


def test_events_endpoint_type_filter_and_limit(tmp_path):
    client, store = _app(tmp_path, _ok_handler)
    client.post("/api/v1/responses", json=_request())
    client.post("/api/v1/responses", json=_request())

    only = client.get("/api/events?type=request").json()["events"]
    assert len(only) == 2
    assert all(e["type"] == "request" for e in only)

    wrong = client.get("/api/events?type=key_switch").json()["events"]
    assert wrong == []

    limited = client.get("/api/events?limit=1").json()["events"]
    assert len(limited) == 1
    store.close()


# ---- request 事件内容（AC5）----

def test_request_event_success_content(tmp_path):
    """成功 request 事件：request_id/成功/耗时/协议/模型/尝试链/token，且无明文 key。"""
    client, store = _app(tmp_path, _ok_handler)
    client.post("/api/v1/responses", json=_request())

    rows = store.query_events(limit=10)
    ev = rows[0]
    data = ev["data"]
    assert data["success"] is True
    assert data["status_code"] == 200
    assert data["protocol"] == "responses"
    assert data["model"] == "gpt-5.6-luna"
    assert data["stream"] is False
    assert data["account_id"] == "a1"
    assert data["attempt_count"] == 1
    assert data["attempts"][0]["result"] == "success"
    assert data["token"] == {"prompt": 7, "completion": 3}
    assert data["error"] is None
    assert isinstance(data["duration_ms"], int)
    # meta 带 request_id；data/meta 全量无明文密钥痕迹
    assert data["request_id"] == ev["meta"]["request_id"]
    blob = str(data) + str(ev["meta"])
    assert "sk-1111" not in blob and "sk-2222" not in blob
    store.close()


def test_request_event_stream_success(tmp_path):
    """流式成功：request 事件仍记录（token 记 0）。"""
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            stream=httpx.ByteStream(b'data: {"type":"response.completed"}\n\n'),
            headers={"content-type": "text/event-stream"},
        )

    client, store = _app(tmp_path, handler)
    with client.stream("POST", "/api/v1/responses", json=_request(stream=True)) as resp:
        assert resp.status_code == 200
        list(resp.iter_raw())  # 消费完

    rows = store.query_events(limit=10)
    data = rows[0]["data"]
    assert data["success"] is True
    assert data["stream"] is True
    assert data["token"] == {"prompt": 0, "completion": 0}
    store.close()


def test_request_event_bad_request(tmp_path):
    """400：request 事件 success=False + error 类型 bad_request，账号不进入冷却。"""
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": {"message": "bad model"}})

    client, store = _app(tmp_path, handler)
    resp = client.post("/api/v1/responses", json=_request())
    assert resp.status_code == 400

    rows = store.query_events(limit=10)
    types = [e["type"] for e in rows]
    assert "all_keys_invalid" not in types
    assert "all_keys_unavailable" not in types
    data = rows[0]["data"]
    assert data["success"] is False
    assert data["status_code"] == 400
    assert data["error"]["type"] == "bad_request"
    store.close()


# ---- 切换与全失效（AC3）----

def test_quota_switch_emits_switch_and_request(tmp_path):
    """429 → 切到 a2 成功：key_switch + key_cooldown_started + request(success)。"""
    def handler(req: httpx.Request) -> httpx.Response:
        auth = req.headers.get("authorization", "")
        if "sk-1111" in auth:
            return httpx.Response(429, json={"error": {"message": "rate limit"}})
        return _ok_handler(req)

    client, store = _app(tmp_path, handler)
    resp = client.post("/api/v1/responses", json=_request())
    assert resp.status_code == 200
    assert resp.headers.get("x-pool-account") == "a2"

    rows = store.query_events(limit=10)
    types = {e["type"] for e in rows}
    assert "key_switch" in types
    assert "key_cooldown_started" in types
    assert "all_keys_invalid" not in types
    assert "all_keys_unavailable" not in types

    sw = next(e for e in rows if e["type"] == "key_switch")
    assert sw["data"]["from_account_id"] == "a1"
    assert sw["data"]["to_account_id"] == "a2"
    assert sw["data"]["error_type"] == "quota"
    assert sw["data"]["request_id"] == sw["meta"]["request_id"]

    req_ev = next(e for e in rows if e["type"] == "request")
    assert req_ev["data"]["success"] is True
    assert req_ev["data"]["account_id"] == "a2"
    assert req_ev["data"]["attempt_count"] == 2
    assert [a["result"] for a in req_ev["data"]["attempts"]] == ["error", "success"]
    store.close()


def test_all_quota_emits_all_keys_invalid(tmp_path):
    """全部 429：all_keys_invalid + request(success=False, 503)。"""
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": {"message": "rate limit"}})

    client, store = _app(tmp_path, handler)
    resp = client.post("/api/v1/responses", json=_request())
    assert resp.status_code == 503

    rows = store.query_events(limit=10)
    types = {e["type"] for e in rows}
    assert "all_keys_invalid" in types
    assert "all_keys_unavailable" not in types
    inv = next(e for e in rows if e["type"] == "all_keys_invalid")
    assert sorted(inv["data"]["attempted_account_ids"]) == ["a1", "a2"]
    assert inv["data"]["error_types"] == ["quota"]
    assert inv["data"]["attempt_count"] == 2
    req_ev = next(e for e in rows if e["type"] == "request")
    assert req_ev["data"]["success"] is False
    assert req_ev["data"]["status_code"] == 503
    store.close()


def test_all_network_errors_emit_all_keys_unavailable(tmp_path):
    """全部网络错：all_keys_unavailable（非 invalid）。"""
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=req)

    client, store = _app(tmp_path, handler)
    resp = client.post("/api/v1/responses", json=_request())
    assert resp.status_code == 503

    rows = store.query_events(limit=10)
    types = {e["type"] for e in rows}
    assert "all_keys_unavailable" in types
    assert "all_keys_invalid" not in types
    una = next(e for e in rows if e["type"] == "all_keys_unavailable")
    assert sorted(una["data"]["attempted_account_ids"]) == ["a1", "a2"]
    assert una["data"]["error_types"] == ["network"]
    store.close()


def test_no_healthy_emits_all_keys_unavailable(tmp_path):
    """无健康账号（0 次尝试）：all_keys_unavailable（attempt_count=0）。"""
    client, store = _app(
        tmp_path,
        _ok_handler,
        accounts=[Account(id="a1", name="A1", api_key="sk-1111", enabled=False)],
    )
    resp = client.post("/api/v1/responses", json=_request())
    assert resp.status_code == 503

    rows = store.query_events(limit=10)
    una = next(e for e in rows if e["type"] == "all_keys_unavailable")
    assert una["data"]["attempted_account_ids"] == []
    assert una["data"]["attempt_count"] == 0
    req_ev = next(e for e in rows if e["type"] == "request")
    assert req_ev["data"]["error"]["type"] == "no_healthy"
    store.close()


# ---- 网关 key 事件（AC4）----

def test_gateway_key_events(tmp_path):
    """创建/吊销网关 key 产生 gateway_key_created / gateway_key_revoked（无明文）。"""
    client, store = _app(tmp_path, _ok_handler)

    resp = client.post("/api/keys", json={"label": "ftre"})
    assert resp.status_code == 201
    created = resp.json()

    rows = store.query_events(limit=10)
    ev = rows[0]
    assert ev["type"] == "gateway_key_created"
    assert ev["data"]["key_id"] == created["id"]
    assert ev["data"]["label"] == "ftre"
    assert "key" not in ev["data"]  # 不含明文
    blob = str(ev["data"]) + str(ev["meta"])
    assert created["key"] not in blob and "gk-" not in blob

    assert client.delete(f"/api/keys/{created['id']}").json()["ok"] is True
    rows = store.query_events(limit=10)
    rev = rows[0]
    assert rev["type"] == "gateway_key_revoked"
    assert rev["data"]["key_id"] == created["id"]
    assert rev["data"]["label"] == "ftre"
    store.close()