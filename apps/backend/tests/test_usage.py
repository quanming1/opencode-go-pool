"""usage 存储层与 recorder 单测（C2）。"""

from opencode_pool.store.sqlite_store import AccountStore
from opencode_pool.usage.recorder import UsageRecorder, kind_label


def _store(tmp_path) -> AccountStore:
    return AccountStore(str(tmp_path / "usage.db"))


def test_save_and_aggregate_buckets(tmp_path):
    store = _store(tmp_path)
    # 注入固定 ts（跨小时验证桶聚合）
    store.save_usage(
        "2026-08-20T08:30:00",
        "a1",
        "success",
        prompt_tokens=100,
        completion_tokens=50,
    )
    store.save_usage(
        "2026-08-20T08:45:00",
        "a1",
        "success",
        prompt_tokens=200,
        completion_tokens=60,
    )
    store.save_usage("2026-08-20T09:10:00", "a2", "error", error_type="quota")

    agg = store.aggregate_usage(hours=24)
    # totals
    assert agg["totals"]["request_count"] == 3
    assert agg["totals"]["prompt_tokens"] == 300
    assert agg["totals"]["completion_tokens"] == 110
    assert agg["totals"]["error_count"] == 1
    # buckets：08 与 09 两桶
    buckets = {b["ts"].split("T")[1]: b for b in agg["buckets"]}
    assert "08:00:00" in buckets
    assert buckets["08:00:00"]["request_count"] == 2
    assert buckets["09:00:00"]["request_count"] == 1
    assert buckets["09:00:00"]["error_count"] == 1
    # per_account
    per = {p["account_id"]: p for p in agg["per_account"]}
    assert per["a1"]["request_count"] == 2
    assert per["a2"]["request_count"] == 1
    store.close()


def test_empty_store_stats_all_zero(tmp_path):
    store = _store(tmp_path)
    agg = store.aggregate_usage(hours=24)
    assert agg["totals"] == {
        "request_count": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "error_count": 0,
    }
    assert agg["per_account"] == []
    assert agg["buckets"] == []
    store.close()


def test_usage_recorder_stats_roundtrip(tmp_path):
    store = _store(tmp_path)
    rec = UsageRecorder(store)
    rec.record("a1", "success", prompt_tokens=10, completion_tokens=5)
    rec.record("a1", "error", error_type="quota")
    stats = rec.stats(hours=24)
    assert stats["totals"]["request_count"] == 2
    assert stats["totals"]["error_count"] == 1
    store.close()


def test_switch_history_with_labels(tmp_path):
    store = _store(tmp_path)
    store.write_event("2026-08-20T09:00:00", "a1", "quota", "rate limit")
    rec = UsageRecorder(store)
    events = rec.switch_history(limit=10)
    assert len(events) == 1
    assert events[0]["kind"] == "quota"
    assert events[0]["kind_label"] == "额度限制"
    store.close()


def test_kind_label_mapping():
    assert kind_label("quota") == "额度限制"
    assert kind_label("auth") == "鉴权失败"
    assert kind_label("recover") == "恢复"
    assert kind_label("unknown") == "unknown"
