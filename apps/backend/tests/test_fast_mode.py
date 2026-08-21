"""FAST_MODE 快路径单测（G8 FR4/FR5，AC1/AC2/AC4）。

覆盖：
- UsageRecorder fast 模式：成功 record 不落 usage_events、StatsSummary 由
  内存聚合生成（含 mode 字段与 event_counts 合并）；
- EventRecorder fast 模式：成功 request 事件短路（不构造不落库），
  失败/状态事件完整保留；
- 独立实例端到端：fast 模式下请求成功后 DB 无成功事件、stats.mode=fast。
"""

import pytest

from opencode_pool.events.recorder import EventRecorder, EventType
from opencode_pool.store.sqlite_store import AccountStore
from opencode_pool.usage.recorder import UsageRecorder


@pytest.fixture
def store(tmp_path) -> AccountStore:
    s = AccountStore(str(tmp_path / "test.db"))
    assert s.available
    yield s
    s.close()


def test_fast_usage_record_skips_db_and_updates_metrics(store):
    rec = UsageRecorder(store, fast_mode=True)
    rec.record("acc-1", kind="success", prompt_tokens=10, completion_tokens=5)
    rec.record("acc-1", kind="error", error_type="quota")
    # usage_events 无任何新记录
    assert store.aggregate_usage(hours=24)["totals"]["request_count"] == 0


def test_fast_stats_contract_and_mode(store):
    rec = UsageRecorder(store, fast_mode=True)
    rec.record(
        "acc-1", kind="success", prompt_tokens=10, completion_tokens=5,
        duration_ms=120, protocol="responses",
    )
    data = rec.stats(hours=24)
    assert data["mode"] == "fast"
    assert data["totals"]["request_count"] == 1
    assert data["totals"]["success_rate"] == 1.0
    assert data["totals"]["prompt_tokens"] == 10
    assert data["summary"]["duration_ms"]["avg"] == 120.0
    assert data["summary"]["protocol"] == [{"name": "responses", "count": 1}]
    # event_counts 从 DB 状态事件合并（空库默认结构）
    assert data["summary"]["event_counts"]["key_switch"] == 0


def test_normal_stats_mode_field_and_behavior(store):
    """normal 模式带 mode=normal，且行为与 G7 一致（同步直写）。"""
    rec = UsageRecorder(store)  # 无 writer = 同步直写
    rec.record("acc-1", kind="success")
    data = rec.stats(hours=24)
    assert data["mode"] == "normal"
    assert data["totals"]["request_count"] == 1


def test_fast_event_recorder_skips_success_request_only(store):
    rec = EventRecorder(store, fast_mode=True)
    rec.record(
        EventType.REQUEST,
        {"success": True, "request_id": "r1"},
        {"source": "forwarder"},
    )
    # 成功 request 事件：不落库
    assert store.query_events(limit=10) == []
    # 失败 request 事件：保留
    rec.record(
        EventType.REQUEST,
        {"success": False, "request_id": "r2", "error": {"type": "quota"}},
    )
    rows = store.query_events(limit=10)
    assert len(rows) == 1
    assert rows[0]["type"] == "request"
    # 状态事件：保留
    rec.record(EventType.KEY_SWITCH, {"from": "acc-1", "to": "acc-2"})
    rows = store.query_events(limit=10, types=["key_switch"])
    assert len(rows) == 1


def test_fast_event_recorder_normal_mode_keeps_success(store):
    rec = EventRecorder(store)  # fast_mode=False
    rec.record(EventType.REQUEST, {"success": True, "request_id": "r1"})
    rows = store.query_events(limit=10)
    assert len(rows) == 1
    assert rows[0]["type"] == "request"


def test_fast_droppable_flag_forwarded_to_writer(store, tmp_path):
    """normal 模式：成功 request 标 droppable——满载时不可丢任务驱逐最旧 droppable。"""
    import threading
    import time

    from opencode_pool.store.writer import SQLiteWriter

    writer = SQLiteWriter(maxsize=2)
    rec = EventRecorder(store, writer=writer)
    gate = threading.Event()
    try:

        def _blocked() -> None:
            gate.wait(2.0)  # 占住写线程（消除调度竞态）

        writer.submit(_blocked)  # 执行中（gate 阻塞）
        # 等待 worker 取出阻塞任务（进入执行态）
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline and len(writer._items) > 0:  # noqa: SLF001
            time.sleep(0.005)
        rec.record(EventType.REQUEST, {"success": True})   # 队列 [droppable]
        rec.record(EventType.REQUEST, {"success": True})   # 队列满（len=2）
        # 状态事件不可丢：驱逐最旧 droppable（索引 0 的 success REQUEST）腾位入队
        rec.record(EventType.KEY_SWITCH, {"from": "a", "to": "b"})
        gate.set()
        writer.flush()
        assert writer.dropped == 1
        rows = store.query_events(limit=10)
        types = sorted(r["type"] for r in rows)
        # 剩余：第 1 个 success request + key_switch（第 2 个 request 被驱逐）
        assert types == ["key_switch", "request"]
    finally:
        gate.set()
        writer.close()


def create_fast_app(tmp_path, monkeypatch):
    """构建 FAST_MODE 独立实例（复用 conftest 的隔离模式）。"""
    from opencode_pool import app as app_module

    monkeypatch.setattr(app_module.settings, "db_path", str(tmp_path / "fast.db"))
    monkeypatch.setattr(app_module.settings, "fast_mode", True)
    # 空账号池配置文件（可启动）
    cfg = tmp_path / "accounts.yaml"
    cfg.write_text("accounts: []\n", encoding="utf-8")
    return app_module.create_app(config_path=str(cfg))


def test_fast_app_stats_endpoint(tmp_path, monkeypatch):
    """端到端：FAST_MODE 实例 /api/stats 返回 mode=fast 且契约完整。"""
    from fastapi.testclient import TestClient

    app = create_fast_app(tmp_path, monkeypatch)
    with TestClient(app) as client:
        resp = client.get("/api/stats?hours=24")
        assert resp.status_code == 200
        data = resp.json()
        assert data["mode"] == "fast"
        assert "totals" in data and "per_account" in data
        assert "per_account_models" in data and "buckets" in data
        assert "error_types" in data and "summary" in data


def test_fast_app_usages_recorder_does_not_persist(tmp_path, monkeypatch):
    """端到端：fast 实例成功转发后 usage_events/events 无成功记录。"""
    from fastapi.testclient import TestClient

    app = create_fast_app(tmp_path, monkeypatch)

    with TestClient(app):
        recorder = app.state.usage_recorder
        # 直接驱动 recorder（fake 上游转发在 test_proxy 体系已覆盖；
        # 这里验证 fast 路径的落库短路）
        recorder.record("acc-1", kind="success", prompt_tokens=7)
        recorder.record("acc-1", kind="error", error_type="auth")
        store = app.state.event_recorder._store  # noqa: SLF001 - 集成断言
        # usage_events 无记录（成功+失败都不落 usage_events——失败计数在内存）
        assert store.aggregate_usage(hours=24)["totals"]["request_count"] == 0
        # events 无成功 request 事件（EventRecorder fast 短路）
        rows = store.query_events(limit=10)
        assert rows == []
        # stats 反映内存聚合
        data = recorder.stats(hours=24)
        assert data["totals"]["request_count"] == 2
        assert data["totals"]["success_rate"] == 0.5
        assert data["error_types"] == [{"type": "auth", "count": 1}]