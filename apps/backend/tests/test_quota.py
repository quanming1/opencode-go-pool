"""额度查询服务单测（C5）：解析、TTL 缓存、force 刷新、降级、汇总。"""

import datetime as _dt

import httpx
import pytest

from opencode_pool.accounts.models import Account
from opencode_pool.accounts.pool import AccountPool
from opencode_pool.quota.service import QuotaService, _parse_window

# anyio（fastapi/httpx 传递依赖，自带 pytest 插件）驱动 async 测试；同步测试不受影响
pytestmark = pytest.mark.anyio


def _usage_body(rolling_p=2, weekly_p=74, monthly_p=44, weekly_status="ok"):
    return {
        "usage": {
            "rolling": {
                "status": "ok",
                "percent": rolling_p,
                "resetsAt": "2026-08-20T14:09:31Z",
            },
            "weekly": {
                "status": weekly_status,
                "percent": weekly_p,
                "resetsAt": "2026-08-24T00:00:00Z",
            },
            "monthly": {
                "status": "ok",
                "percent": monthly_p,
                "resetsAt": "2026-09-19T05:54:29Z",
            },
        }
    }


def _fake_now():
    """固定时钟：2026-08-20T12:00:00Z（rolling 还有 ~2h5m 到期）。"""
    return lambda: _dt.datetime(2026, 8, 20, 12, 0, 0, tzinfo=_dt.UTC)


# ---- 窗口解析 ----

def test_parse_window_full():
    w = _parse_window(
        {"status": "ok", "percent": 50, "resetsAt": "2026-08-20T13:00:00Z"},
        _dt.datetime(2026, 8, 20, 12, 0, 0, tzinfo=_dt.UTC),
    )
    assert w["status"] == "ok"
    assert w["percent"] == 50
    assert w["resets_at"] == "2026-08-20T13:00:00Z"
    assert w["resets_in_seconds"] == 3600


def test_parse_window_expired_clamps_to_zero():
    w = _parse_window(
        {"status": "ok", "percent": 99, "resetsAt": "2026-08-20T11:00:00Z"},
        _dt.datetime(2026, 8, 20, 12, 0, 0, tzinfo=_dt.UTC),
    )
    assert w["resets_in_seconds"] == 0


@pytest.mark.parametrize(
    "bad",
    [
        None,
        "string",
        {"status": "ok"},  # 缺 percent
        {"status": 1, "percent": 5},  # status 类型错
        {"status": "ok", "percent": "50"},  # percent 类型错
    ],
)
def test_parse_window_malformed_returns_none(bad):
    assert _parse_window(bad, _dt.datetime(2026, 8, 20, tzinfo=_dt.UTC)) is None


# ---- 服务：正常解析 + 汇总 ----

async def test_fetch_parses_windows_and_summary():
    calls: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(req.headers.get("authorization", ""))
        return httpx.Response(200, json=_usage_body(rolling_p=10, weekly_p=80, monthly_p=40))

    pool = AccountPool(
        accounts=[
            Account(id="a1", name="A1", api_key="sk-1111", base_url="http://fake/v1"),
            Account(id="a2", name="A2", api_key="sk-2222", base_url="http://fake/v1"),
        ]
    )
    svc = QuotaService(
        pool,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        now=_fake_now(),
    )
    data = await svc.fetch()

    assert data["cached"] is False
    assert len(data["accounts"]) == 2
    q = data["accounts"][0]["quota"]
    assert q["rolling"]["percent"] == 10
    assert q["rolling"]["resets_in_seconds"] == 2 * 3600 + 9 * 60 + 31  # 14:09:31 - 12:00
    assert q["weekly"]["percent"] == 80
    # 请求带账号密钥（发往上游）
    assert calls == ["Bearer sk-1111", "Bearer sk-2222"]

    s = data["summary"]
    assert s["total_accounts"] == 2
    assert s["queried"] == 2
    assert s["ok_accounts"] == 2
    assert s["rolling_available"] == 2
    assert s["weekly_avg_percent"] == 80
    assert s["monthly_avg_percent"] == 40
    assert s["allocated_usd"] == {"rolling": 24, "weekly": 60, "monthly": 120}
    assert s["estimated_used_usd"] == {"rolling": 2, "weekly": 48, "monthly": 48}


# ---- TTL 缓存 ----

async def test_cache_hit_skips_upstream():
    counter = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        counter["n"] += 1
        return httpx.Response(200, json=_usage_body())

    pool = AccountPool(
        accounts=[Account(id="a1", name="A1", api_key="sk-1111", base_url="http://fake/v1")]
    )
    svc = QuotaService(
        pool,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        cache_ttl=60,
        now=_fake_now(),
    )

    first = await svc.fetch()
    assert first["cached"] is False
    second = await svc.fetch()
    assert second["cached"] is True
    assert counter["n"] == 1  # 缓存期内不打上游
    assert second["accounts"] == first["accounts"]


async def test_force_refresh_bypasses_cache():
    counter = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        counter["n"] += 1
        return httpx.Response(200, json=_usage_body())

    pool = AccountPool(
        accounts=[Account(id="a1", name="A1", api_key="sk-1111", base_url="http://fake/v1")]
    )
    svc = QuotaService(
        pool,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        now=_fake_now(),
    )
    await svc.fetch()
    await svc.fetch(force=True)
    assert counter["n"] == 2


async def test_cache_expires_after_ttl():
    counter = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        counter["n"] += 1
        return httpx.Response(200, json=_usage_body())

    pool = AccountPool(
        accounts=[Account(id="a1", name="A1", api_key="sk-1111", base_url="http://fake/v1")]
    )
    clock = {"t": _dt.datetime(2026, 8, 20, 12, 0, 0, tzinfo=_dt.UTC)}
    svc = QuotaService(
        pool,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        cache_ttl=60,
        now=lambda: clock["t"],
    )
    await svc.fetch()
    clock["t"] += _dt.timedelta(seconds=61)  # 越过 TTL
    data = await svc.fetch()
    assert data["cached"] is False
    assert counter["n"] == 2


# ---- 降级 ----

async def test_single_account_401_degrades():
    def handler(req: httpx.Request) -> httpx.Response:
        if "sk-1111" in req.headers.get("authorization", ""):
            return httpx.Response(401, json={"error": "unauthorized"})
        return httpx.Response(200, json=_usage_body())

    pool = AccountPool(
        accounts=[
            Account(id="a1", name="A1", api_key="sk-1111", base_url="http://fake/v1"),
            Account(id="a2", name="A2", api_key="sk-2222", base_url="http://fake/v1"),
        ]
    )
    svc = QuotaService(
        pool,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        now=_fake_now(),
    )
    data = await svc.fetch()
    by_id = {a["account_id"]: a for a in data["accounts"]}
    assert by_id["a1"]["quota"] is None
    assert by_id["a1"]["error"] == "http 401"
    assert by_id["a2"]["quota"] is not None  # 其他账号不受影响

    s = data["summary"]
    assert s["ok_accounts"] == 1
    assert s["total_accounts"] == 2
    # 均值只统计成功账号
    assert s["rolling_avg_percent"] == 2


async def test_malformed_body_degrades():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": True})

    pool = AccountPool(
        accounts=[Account(id="a1", name="A1", api_key="sk-1111", base_url="http://fake/v1")]
    )
    svc = QuotaService(
        pool,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        now=_fake_now(),
    )
    data = await svc.fetch()
    assert data["accounts"][0]["quota"] is None
    assert data["accounts"][0]["error"] == "missing usage"
    assert data["summary"]["ok_accounts"] == 0


async def test_network_error_degrades():
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=req)

    pool = AccountPool(
        accounts=[Account(id="a1", name="A1", api_key="sk-1111", base_url="http://fake/v1")]
    )
    svc = QuotaService(
        pool,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        now=_fake_now(),
    )
    data = await svc.fetch()
    assert data["accounts"][0]["quota"] is None
    assert data["accounts"][0]["error"] == "ConnectError"


# ---- 账号过滤 ----

async def test_disabled_account_not_queried():
    counter = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        counter["n"] += 1
        return httpx.Response(200, json=_usage_body())

    pool = AccountPool(
        accounts=[
            Account(id="a1", name="A1", api_key="sk-1111", base_url="http://fake/v1"),
            Account(
                id="a2", name="A2", api_key="sk-2222", base_url="http://fake/v1", enabled=False
            ),
        ]
    )
    svc = QuotaService(
        pool,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        now=_fake_now(),
    )
    data = await svc.fetch()
    assert counter["n"] == 1  # disabled 不打上游
    assert [a["account_id"] for a in data["accounts"]] == ["a1"]
    assert data["summary"]["total_accounts"] == 1


async def test_rate_limited_window_counted():
    """weekly rate-limited 的账号：rolling_available 只看 rolling 窗口。"""

    def handler(req: httpx.Request) -> httpx.Response:
        body = _usage_body(rolling_p=100, weekly_p=100, weekly_status="rate-limited")
        return httpx.Response(200, json=body)

    pool = AccountPool(
        accounts=[Account(id="a1", name="A1", api_key="sk-1111", base_url="http://fake/v1")]
    )
    svc = QuotaService(
        pool,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        now=_fake_now(),
    )
    data = await svc.fetch()
    q = data["accounts"][0]["quota"]
    assert q["weekly"]["status"] == "rate-limited"
    assert q["weekly"]["percent"] == 100
    # rolling 仍 ok（percent=100 但 status=ok → 计入 available）
    assert data["summary"]["rolling_available"] == 1
