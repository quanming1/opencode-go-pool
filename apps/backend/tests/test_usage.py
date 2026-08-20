"""usage 存储层与 recorder 单测（C2 + D1）。

C4 后：switch_history / kind_label 已删除，状态类事件统一走 events 模块
（见 test_events.py）。
D1：新增双协议 token 提取、per_account_models 聚合、recent_usage_rate 速率。
"""

from opencode_pool.proxy.forwarder import _extract_usage
from opencode_pool.store.sqlite_store import AccountStore
from opencode_pool.usage.recorder import UsageRecorder


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


# ---- D1：双协议 token 字段（Chat Completions vs Responses）----

def test_extract_usage_chat_completions_fields():
    """Chat Completions：usage.prompt_tokens / usage.completion_tokens。"""
    body = '{"usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10}}'
    assert _extract_usage(body) == (7, 3)


def test_extract_usage_responses_fields():
    """Responses：usage.input_tokens / usage.output_tokens（字段名不同！）。"""
    body = '{"usage": {"input_tokens": 9, "output_tokens": 4, "total_tokens": 13}}'
    assert _extract_usage(body) == (9, 4)


def test_extract_usage_partial_and_missing():
    """字段缺失/无 usage：缺失位记 0，绝不抛错。"""
    assert _extract_usage('{"usage": {"prompt_tokens": 5}}') == (5, 0)
    assert _extract_usage('{"usage": {"output_tokens": 2}}') == (0, 2)
    assert _extract_usage('{"id": "x"}') == (0, 0)
    assert _extract_usage("not json") == (0, 0)
    assert _extract_usage("") == (0, 0)


# ---- D1：per_account_models 聚合（某 Key 收到多少次请求、分别什么模型）----

def test_aggregate_per_account_models(tmp_path):
    store = _store(tmp_path)
    store.save_usage("2026-08-20T08:00:00", "a1", "success", model="m-a", prompt_tokens=10)
    store.save_usage("2026-08-20T08:01:00", "a1", "success", model="m-a", prompt_tokens=5)
    store.save_usage("2026-08-20T08:02:00", "a1", "error", error_type="quota", model="m-b")
    store.save_usage("2026-08-20T08:03:00", "a2", "success", model="m-a")

    rows = store.aggregate_usage(hours=24)["per_account_models"]
    by = {(r["account_id"], r["model"]): r for r in rows}
    assert by[("a1", "m-a")]["request_count"] == 2
    assert by[("a1", "m-a")]["prompt_tokens"] == 15
    assert by[("a1", "m-a")]["error_count"] == 0
    assert by[("a1", "m-b")]["request_count"] == 1
    assert by[("a1", "m-b")]["error_count"] == 1
    assert by[("a2", "m-a")]["request_count"] == 1
    # 无 model（旧数据）也归组为 None 不丢
    store.save_usage("2026-08-20T08:04:00", "a3", "success", model=None)
    rows = store.aggregate_usage(hours=24)["per_account_models"]
    assert any(r["account_id"] == "a3" and r["model"] is None for r in rows)
    store.close()


def test_aggregate_empty_has_per_account_models(tmp_path):
    store = _store(tmp_path)
    agg = store.aggregate_usage(hours=24)
    assert agg["per_account_models"] == []
    store.close()


# ---- D1：recent_usage_rate 请求/token 速率 ----

def test_recent_usage_rate_counts_recent_window(tmp_path):
    store = _store(tmp_path)
    import datetime as _dt

    now = _dt.datetime.now(_dt.UTC)
    now_iso = now.replace(microsecond=0).isoformat()
    old = (now - _dt.timedelta(minutes=90)).replace(microsecond=0).isoformat()  # 窗口外
    store.save_usage(now_iso, "a1", "success", prompt_tokens=100, completion_tokens=50)
    store.save_usage(now_iso, "a1", "success", prompt_tokens=100, completion_tokens=50)
    store.save_usage(now_iso, "a2", "error", error_type="quota")
    store.save_usage(old, "a1", "success")  # 90 分钟前不计入

    rate = store.recent_usage_rate(minutes=60)
    assert rate["requests"] == 3  # 成功 2 + 错误 1，窗口内
    assert rate["requests_per_minute"] == round(3 / 60, 2)
    assert rate["tokens"] == 300
    assert rate["tokens_per_hour"] == 300
    assert rate["minutes"] == 60
    store.close()


def test_recent_usage_rate_empty(tmp_path):
    store = _store(tmp_path)
    rate = store.recent_usage_rate(minutes=60)
    assert rate["requests"] == 0
    assert rate["requests_per_minute"] == 0.0
    assert rate["tokens_per_hour"] == 0
    store.close()
