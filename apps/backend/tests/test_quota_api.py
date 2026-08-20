"""额度查询 API 集成测试（C5 FR3）。"""

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from opencode_pool.accounts.models import Account
from opencode_pool.accounts.pool import AccountPool
from opencode_pool.quota.service import QuotaService


def _app(tmp_path) -> tuple[TestClient, dict]:
    counter = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        counter["n"] += 1
        return httpx.Response(
            200,
            json={
                "usage": {
                    "rolling": {"status": "ok", "percent": 5, "resetsAt": "2026-08-20T14:09:31Z"},
                    "weekly": {"status": "ok", "percent": 70, "resetsAt": "2026-08-24T00:00:00Z"},
                    "monthly": {"status": "ok", "percent": 45, "resetsAt": "2026-09-19T05:54:29Z"},
                }
            },
        )

    pool = AccountPool(
        accounts=[Account(id="a1", name="A1", api_key="sk-1111", base_url="http://fake/v1")]
    )
    service = QuotaService(
        pool, client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )

    app = FastAPI()
    app.state.account_pool = pool
    app.state.quota_service = service

    from opencode_pool.api.quota import router as quota_router

    app.include_router(quota_router)
    return TestClient(app), counter


def test_quota_endpoint_shape(tmp_path):
    """AC2：/api/quota 结构完整且不含密钥。"""
    client, counter = _app(tmp_path)
    resp = client.get("/api/quota")
    assert resp.status_code == 200
    body = resp.json()

    assert set(body.keys()) == {"accounts", "summary", "fetched_at", "cached"}
    assert body["cached"] is False
    acc = body["accounts"][0]
    assert acc["account_id"] == "a1"
    assert acc["error"] is None
    for w in ("rolling", "weekly", "monthly"):
        win = acc["quota"][w]
        assert set(win.keys()) == {"status", "percent", "resets_at", "resets_in_seconds"}
    s = body["summary"]
    assert s["rolling_avg_percent"] == 5
    assert s["allocated_usd"] == {"rolling": 12, "weekly": 30, "monthly": 60}
    assert s["estimated_used_usd"] == {"rolling": 1, "weekly": 21, "monthly": 27}
    # 脱敏：响应全文无密钥
    assert "sk-1111" not in resp.text


def test_quota_endpoint_cache_and_refresh(tmp_path):
    """缓存命中不打上游；refresh=1 强制刷新。"""
    client, counter = _app(tmp_path)
    client.get("/api/quota")
    assert counter["n"] == 1
    cached = client.get("/api/quota").json()
    assert cached["cached"] is True
    assert counter["n"] == 1
    forced = client.get("/api/quota?refresh=1").json()
    assert forced["cached"] is False
    assert counter["n"] == 2
