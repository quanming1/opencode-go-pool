"""日志概览 API（D1 FR3/FR4）：GET /api/logs/overview。

验证当前活跃 Key、速率、剩余时长推测，以及数据缺失时的降级行为。
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from opencode_pool.events.recorder import EventRecorder, EventType
from opencode_pool.logs.overview import LogsOverview
from opencode_pool.store.sqlite_store import AccountStore


class _FakeQuota:
    """最小 quota 服务：直接返回预设 dict。"""

    def __init__(self, data):
        self._data = data

    async def fetch(self, force: bool = False) -> dict:
        return self._data


def _client(tmp_path, events, quota_data):
    store = AccountStore(str(tmp_path / "logs.db"))
    recorder = EventRecorder(store)
    app = FastAPI()
    app.state.logs_overview = LogsOverview(store, recorder)
    app.state.quota_service = _FakeQuota(quota_data)
    from opencode_pool.api.logs import router as logs_router

    app.include_router(logs_router)

    # 预填 events 供当前活跃 Key 识别
    if events:
        for type_, data in events:
            recorder.record(type_, data)
    return TestClient(app), store


def test_overview_active_rate_and_remaining(tmp_path):
    """有最近成功请求 + 额度摘要 → current_active/rate/usage_remaining 齐全。"""
    import datetime as _dt

    client, store = _client(
        tmp_path,
        events=[
            (EventType.REQUEST.value, {"success": True, "account_id": "a2"}),
            (EventType.REQUEST.value, {"success": False, "account_id": "a1"}),
        ],
        quota_data={
            "summary": {"rolling_avg_percent": 20, "total_accounts": 2},
            "cached": True,
        },
    )
    now = _dt.datetime.now(_dt.UTC).replace(microsecond=0).isoformat()
    store.save_usage(now, "a2", "success", prompt_tokens=10)

    body = client.get("/api/logs/overview").json()
    assert body["current_active"] is not None
    assert body["current_active"]["account_id"] == "a2"
    assert body["rate"]["minutes"] == 60
    # usage_remaining：percent=20,total=2 → 剩 (1-0.2)*2000*2=3200；分钟内有 1 个请求
    rem = body["usage_remaining"]
    assert rem is not None
    assert rem["estimated_requests_left"] == 3200
    assert rem["estimated_hours_left"] > 0
    assert rem["basis"] == "rolling_percent_and_local_rate"
    store.close()


def test_overview_no_quota_remaining_null(tmp_path):
    """额度摘要缺失 → usage_remaining 为 null，其余仍可用。"""
    client, store = _client(
        tmp_path,
        events=[(EventType.REQUEST.value, {"success": True, "account_id": "a1"})],
        quota_data={"summary": {"total_accounts": 0}},
    )
    body = client.get("/api/logs/overview").json()
    assert body["current_active"]["account_id"] == "a1"
    assert body["usage_remaining"] is None
    assert body["rate"]["requests_per_minute"] >= 0
    store.close()


def test_overview_no_activity_all_null(tmp_path):
    """无任何事件/用量 → current_active=None、rate 全 0、usage_remaining=None。"""
    client, store = _client(tmp_path, events=[], quota_data=None)
    body = client.get("/api/logs/overview").json()
    assert body["current_active"] is None
    assert body["rate"]["requests_per_minute"] == 0.0
    assert body["rate"]["tokens_per_hour"] == 0
    assert body["usage_remaining"] is None
    store.close()
