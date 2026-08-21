"""SQLiteWriter 单测（G7 FR7）：异步落库队列的入队/flush/降级/close。"""

from opencode_pool.events.recorder import EventRecorder
from opencode_pool.store.sqlite_store import AccountStore
from opencode_pool.store.writer import SQLiteWriter
from opencode_pool.usage.recorder import UsageRecorder


def _store(tmp_path):
    return AccountStore(str(tmp_path / "w.db"))


def test_submit_then_flush_persists(tmp_path):
    """入队后未 flush 不可见；flush 后可见（异步落库语义）。"""
    store = _store(tmp_path)
    writer = SQLiteWriter()
    try:
        writer.submit(store.save_usage, "2026-01-01T00:00:00", "a1", "success", None, 10, 20, None)
        # 不 flush：可能已落也可能未落（异步），但这里断言 flush 后必然可见
        writer.flush()
        rows = store.aggregate_usage(24)
        assert rows["totals"]["prompt_tokens"] == 10
        assert rows["totals"]["completion_tokens"] == 20
    finally:
        writer.close()


def test_multiple_tasks_ordered(tmp_path):
    """多条提交按序落库。"""
    store = _store(tmp_path)
    writer = SQLiteWriter()
    try:
        for i in range(5):
            writer.submit(
                store.save_usage, f"2026-01-01T00:0{i}:00", "a1", "success", None, i, 0, None
            )
        writer.flush()
        rows = store.aggregate_usage(24)
        assert rows["totals"]["request_count"] == 5
    finally:
        writer.close()


def test_failure_degrades_and_keeps_going(tmp_path):
    """单个任务抛异常：降级记日志，后续任务不受影响。"""
    store = _store(tmp_path)
    writer = SQLiteWriter()
    try:

        def boom():
            raise RuntimeError("boom")

        writer.submit(boom)
        writer.submit(store.save_usage, "2026-01-01T00:00:00", "a1", "success", None, 1, 2, None)
        writer.flush()
        rows = store.aggregate_usage(24)
        assert rows["totals"]["request_count"] == 1
    finally:
        writer.close()


def test_close_stops_thread(tmp_path):
    """close 发送哨兵并等待线程退出；close 幂等。"""
    writer = SQLiteWriter()
    writer.close()
    # 线程已退出；close 幂等
    writer.close()


def test_recorder_writer_mode(tmp_path):
    """EventRecorder/UsageRecorder 注入 writer：record 仅入队，flush 后事件/用量可见。"""
    store = _store(tmp_path)
    writer = SQLiteWriter()
    try:
        events = EventRecorder(store, writer=writer)
        usage = UsageRecorder(store, writer=writer)
        events.record("request", {"success": True})
        usage.record("a1", "success", prompt_tokens=7, completion_tokens=3)
        # 未 flush 时可能不可见（异步）；flush 后必然可见
        writer.flush()
        ev_rows = store.query_events(limit=10)
        assert len(ev_rows) == 1
        assert ev_rows[0]["type"] == "request"
        agg = store.aggregate_usage(24)
        assert agg["totals"]["prompt_tokens"] == 7
    finally:
        writer.close()


def test_recorder_sync_mode_default(tmp_path):
    """默认（无 writer）保持同步直写：record 返回后立即可见。"""
    store = _store(tmp_path)
    events = EventRecorder(store)
    usage = UsageRecorder(store)
    events.record("request", {"success": True})
    usage.record("a1", "success", prompt_tokens=1)
    assert len(store.query_events(limit=10)) == 1
    assert store.aggregate_usage(24)["totals"]["prompt_tokens"] == 1