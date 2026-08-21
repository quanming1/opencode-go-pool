"""FastMetrics 内存聚合器单测（G8 FR2/AC1/AC4）。

覆盖：update/snapshot 结构契约、成功/失败计数、token 聚合、耗时样本
上限与 p95 近似、协议/错误类型分布、窗口滚动裁剪（有界保证）。
"""


from opencode_pool.metrics.fast import (
    FAST_DURATION_SAMPLES,
    FAST_WINDOW_HOURS,
    FastMetrics,
)


def _ts(hour: int = 8, minute: int = 30) -> str:
    """测试用 ISO 时间串（2026-08-21T08:30:00 等）。"""
    return f"2026-08-21T{hour:02d}:{minute:02d}:00"


def test_snapshot_structure_matches_stats_contract():
    m = FastMetrics()
    m.update(
        ts=_ts(), account_id="acc-1", model="gpt-x", success=True,
        prompt_tokens=10, completion_tokens=20, duration_ms=100,
        protocol="chat/completions",
    )
    data = m.snapshot(hours=24)
    # 字段契约与 aggregate_usage + summary 兼容（E4 结构）
    assert "totals" in data and "per_account" in data
    assert "per_account_models" in data and "buckets" in data
    assert "error_types" in data and "summary" in data
    t = data["totals"]
    assert t["request_count"] == 1 and t["success_count"] == 1
    assert t["prompt_tokens"] == 10 and t["completion_tokens"] == 20
    assert t["success_rate"] == 1.0 and t["error_count"] == 0
    assert data["per_account"][0]["account_id"] == "acc-1"
    assert data["per_account"][0]["error_count"] == 0
    assert data["per_account_models"][0]["model"] == "gpt-x"
    assert len(data["buckets"]) == 1
    assert data["buckets"][0]["request_count"] == 1
    # summary：耗时 / 协议（单样本 p95=None，与 events_summary 口径一致）
    s = data["summary"]
    assert s["duration_ms"]["avg"] == 100.0
    assert s["duration_ms"]["max"] == 100.0
    assert s["duration_ms"]["p95"] is None
    assert s["protocol"] == [{"name": "chat/completions", "count": 1}]
    # 空 error_types
    assert data["error_types"] == []


def test_failure_updates_counts_and_error_types():
    m = FastMetrics()
    m.update(ts=_ts(), account_id="acc-1", model=None, success=False, error_type="quota")
    data = m.snapshot(hours=24)
    t = data["totals"]
    assert t["request_count"] == 1 and t["success_count"] == 0
    assert t["success_rate"] == 0.0 and t["error_count"] == 1
    assert data["error_types"] == [{"type": "quota", "count": 1}]
    # 失败不产生 per_account_models（model=None 不归组，与 DB 语义一致）
    assert data["per_account_models"] == []


def test_per_account_and_models_grouping():
    m = FastMetrics()
    for _ in range(3):
        m.update(ts=_ts(), account_id="acc-1", model="gpt-x", success=True, prompt_tokens=1)
    m.update(ts=_ts(), account_id="acc-2", model="gpt-y", success=False, error_type="auth")
    data = m.snapshot(hours=24)
    by_id = {p["account_id"]: p for p in data["per_account"]}
    assert by_id["acc-1"]["request_count"] == 3
    assert by_id["acc-1"]["success_count"] == 3
    assert by_id["acc-2"]["request_count"] == 1
    assert by_id["acc-2"]["error_count"] == 1
    models = {p["model"]: p for p in data["per_account_models"]}
    assert models["gpt-x"]["request_count"] == 3
    assert models["gpt-y"]["request_count"] == 1


def test_window_is_bounded():
    """超过窗口上限后最旧桶被裁剪（内存硬上限）。"""
    m = FastMetrics()
    base_day = "2026-08-01T"
    for i in range(FAST_WINDOW_HOURS + 10):
        hour = i % 24
        day = 1 + i // 24
        m.update(
            ts=f"{base_day[:8]}{day:02d}T{hour:02d}:00:00",
            account_id="acc-1",
            model=None,
            success=True,
        )
    assert len(m._buckets) <= FAST_WINDOW_HOURS  # noqa: SLF001 - 单测断言有界
    data = m.snapshot(hours=FAST_WINDOW_HOURS)
    assert len(data["buckets"]) == FAST_WINDOW_HOURS


def test_duration_samples_bounded_p95_approximation():
    """耗时样本超过上限后丢最旧（p95 基于最近样本近似）。"""
    m = FastMetrics()
    # 501 条：前 500 条 100ms，最后 1 条 999ms —— 丢弃最旧后 max 应为 999
    for _i in range(FAST_DURATION_SAMPLES):
        m.update(
            ts=_ts(), account_id="acc-1", model=None, success=True, duration_ms=100
        )
    assert len(m._buckets["2026-08-21T08:00:00"].durations) == FAST_DURATION_SAMPLES  # noqa: SLF001
    m.update(
        ts=_ts(), account_id="acc-1", model=None, success=True, duration_ms=999
    )
    bucket = m._buckets["2026-08-21T08:00:00"]  # noqa: SLF001
    assert len(bucket.durations) == FAST_DURATION_SAMPLES
    data = m.snapshot(hours=24)
    assert data["summary"]["duration_ms"]["max"] == 999.0


def test_snapshot_hours_window_filtering():
    m = FastMetrics()
    m.update(ts=_ts(hour=8), account_id="acc-1", model=None, success=True)
    m.update(ts=_ts(hour=9), account_id="acc-1", model=None, success=True)
    m.update(ts=_ts(hour=10), account_id="acc-1", model=None, success=True)
    data = m.snapshot(hours=1)
    assert data["totals"]["request_count"] == 1
    assert len(data["buckets"]) == 1
    assert data["buckets"][0]["hour"] == "2026-08-21T10:00:00"
    data2 = m.snapshot(hours=3)
    assert data2["totals"]["request_count"] == 3
    assert [b["hour"] for b in data2["buckets"]] == [
        "2026-08-21T10:00:00",
        "2026-08-21T09:00:00",
        "2026-08-21T08:00:00",
    ]


def test_empty_snapshot_defaults():
    m = FastMetrics()
    data = m.snapshot(hours=24)
    assert data["totals"]["request_count"] == 0
    assert data["totals"]["success_rate"] == 1.0
    assert data["per_account"] == []
    assert data["per_account_models"] == []
    assert data["error_types"] == []
    assert data["summary"]["duration_ms"] == {"avg": None, "p95": None, "max": None}
    assert data["summary"]["protocol"] == []


def test_protocol_counts_across_buckets():
    m = FastMetrics()
    m.update(
        ts=_ts(hour=8), account_id="acc-1", model=None, success=True,
        protocol="responses",
    )
    m.update(
        ts=_ts(hour=9), account_id="acc-1", model=None, success=True,
        protocol="chat/completions",
    )
    m.update(
        ts=_ts(hour=10), account_id="acc-1", model=None, success=True,
        protocol="responses",
    )
    data = m.snapshot(hours=24)
    assert data["summary"]["protocol"] == [
        {"name": "responses", "count": 2},
        {"name": "chat/completions", "count": 1},
    ]


def test_update_is_thread_safe():
    """并发 update 不丢计数（record 与 snapshot 分属不同线程）。"""
    import threading

    m = FastMetrics()
    errors: list[BaseException] = []

    def worker(n: int) -> None:
        try:
            for _i in range(n):
                m.update(
                    ts=_ts(hour=8), account_id="acc-1", model=None, success=True
                )
        except BaseException as exc:  # noqa: BLE001 - 测试收集
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(200,)) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    assert m.snapshot(hours=24)["totals"]["request_count"] == 800