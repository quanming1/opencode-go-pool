"""统一事件（C4）存储层与记录器单测：契约、降级、筛选、裁剪、迁移。"""

import sqlite3

from opencode_pool.events.recorder import SCHEMA_VERSION, EventRecorder, EventType
from opencode_pool.store.sqlite_store import AccountStore


def _store(tmp_path, **kw) -> AccountStore:
    return AccountStore(str(tmp_path / "events.db"), **kw)


# ---- 契约 ----

def test_record_and_query_strict_shape(tmp_path):
    """record → query 每项严格含 type/data/meta/time，且 meta 带 schema_version。"""
    store = _store(tmp_path)
    rec = EventRecorder(store)
    rec.record(EventType.REQUEST, {"success": True}, meta={"source": "t"})

    rows = rec.query()
    assert len(rows) == 1
    assert set(rows[0].keys()) == {"type", "data", "meta", "time"}
    assert rows[0]["type"] == "request"
    assert rows[0]["data"] == {"success": True}
    assert rows[0]["meta"]["schema_version"] == SCHEMA_VERSION
    assert rows[0]["meta"]["source"] == "t"
    # time 是 UTC ISO-8601（以 +00:00 结尾）
    assert rows[0]["time"].endswith("+00:00")
    store.close()


def test_record_without_store_degrades(tmp_path):
    """store=None（或无 store）时 record/query 均不抛。"""
    rec = EventRecorder(None)
    rec.record(EventType.KEY_SWITCH, {"from_account_id": "a1"})  # 不抛
    assert rec.query() == []


def test_record_bad_store_degrades():
    """store 抛异常时 record 降级不抛（转发主路径保护）。"""

    class BadStore:
        def save_event(self, *args, **kw):
            raise RuntimeError("disk gone")

    rec = EventRecorder(BadStore())
    rec.record(EventType.REQUEST, {"success": False})  # 不抛


# ---- 筛选与裁剪 ----

def test_query_type_filter(tmp_path):
    store = _store(tmp_path)
    rec = EventRecorder(store)
    rec.record(EventType.REQUEST, {"success": True})
    rec.record(EventType.KEY_SWITCH, {"from_account_id": "a1"})
    rec.record(EventType.REQUEST, {"success": False})

    only_requests = rec.query(types=["request"])
    assert [e["type"] for e in only_requests] == ["request", "request"]
    # 多个类型
    multi = rec.query(types=["request", "key_switch"])
    assert len(multi) == 3
    store.close()


def test_query_limit_and_order(tmp_path):
    """新→旧排序 + limit 限制。"""
    store = _store(tmp_path)
    rec = EventRecorder(store)
    for i in range(5):
        rec.record(EventType.KEY_ENABLED, {"account_id": f"a{i}"})

    rows = rec.query(limit=3)
    assert len(rows) == 3
    assert rows[0]["data"]["account_id"] == "a4"  # 最新在前
    assert rows[2]["data"]["account_id"] == "a2"
    store.close()


def test_store_trims_to_event_limit(tmp_path):
    """store 裁剪到 event_limit 条。"""
    store = _store(tmp_path, event_limit=3)
    rec = EventRecorder(store)
    for i in range(5):
        rec.record(EventType.KEY_ENABLED, {"account_id": f"a{i}"})

    rows = store.query_events(limit=100)
    assert len(rows) == 3
    assert rows[0]["data"]["account_id"] == "a4"
    assert rows[-1]["data"]["account_id"] == "a2"
    store.close()


def test_bad_json_rows_skipped(tmp_path):
    """单条 data_json 损坏 → 跳过该条，不影响其余。"""
    store = _store(tmp_path)
    rec = EventRecorder(store)
    rec.record(EventType.KEY_ENABLED, {"account_id": "ok"})
    # 手动插入一条坏数据（模拟历史损坏）
    conn = store._conn
    conn.execute(
        "INSERT INTO events (type, event_time, data_json, meta_json) VALUES (?, ?, ?, ?)",
        ("request", "2026-08-20T00:00:00+00:00", "{broken", "{}"),
    )
    conn.commit()

    rows = store.query_events(limit=100)
    assert len(rows) == 1
    assert rows[0]["data"]["account_id"] == "ok"
    store.close()


# ---- 迁移 ----

def _make_legacy_db(path: str) -> None:
    """手工造旧库：只含 switch_history 表与两条记录。"""
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE switch_history ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, "
        "account_id TEXT NOT NULL, kind TEXT NOT NULL, reason TEXT)"
    )
    conn.execute(
        "INSERT INTO switch_history (ts, account_id, kind, reason) VALUES (?, ?, ?, ?)",
        ("2026-08-20T09:00:00", "a1", "quota", "rate limit"),
    )
    conn.execute(
        "INSERT INTO switch_history (ts, account_id, kind, reason) VALUES (?, ?, ?, ?)",
        ("2026-08-20T09:05:00", "a2", "recover", "expired"),
    )
    conn.commit()
    conn.close()


def test_migrate_switch_history_on_open(tmp_path):
    """打开旧库自动迁移 → 事件结构完整 + 旧表被 DROP（AC2）。"""
    db = str(tmp_path / "legacy.db")
    _make_legacy_db(db)

    store = AccountStore(db)  # 构造时触发迁移
    conn = store._conn
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='switch_history'"
    ).fetchone()
    assert row is None  # 旧表已删除

    rows = store.query_events(limit=100)
    assert len(rows) == 2
    by_type = {r["type"]: r for r in rows}
    assert "key_cooldown_started" in by_type
    assert "key_cooldown_completed" in by_type
    started = by_type["key_cooldown_started"]
    assert started["data"]["account_id"] == "a1"
    assert started["data"]["error_type"] == "quota"
    assert started["meta"]["source"] == "migrated_switch_history"
    completed = by_type["key_cooldown_completed"]
    assert completed["data"]["account_id"] == "a2"
    assert completed["data"]["previous_status"] == "cooldown"
    assert completed["event_time"] == "2026-08-20T09:05:00"  # 保留原始 ts
    store.close()


def test_migrate_idempotent(tmp_path):
    """已迁移过的库（无旧表）再次打开 → 迁移返回 0，不报错。"""
    db = str(tmp_path / "fresh.db")
    store = AccountStore(db)  # 首次打开即建 events 表
    assert store.migrate_switch_history() == 0
    store.close()


def test_migrate_legacy_kinds(tmp_path):
    """旧 kind 全集映射：disable/enable/clear/auto_disable。"""
    db = str(tmp_path / "legacy2.db")
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE switch_history ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, "
        "account_id TEXT NOT NULL, kind TEXT NOT NULL, reason TEXT)"
    )
    rows = [
        ("2026-08-20T09:00:00", "a1", "disable", "manual"),
        ("2026-08-20T09:01:00", "a1", "enable", "manual"),
        ("2026-08-20T09:02:00", "a1", "clear", "manual"),
        ("2026-08-20T09:03:00", "a1", "auto_disable", "3 fails"),
    ]
    conn.executemany(
        "INSERT INTO switch_history (ts, account_id, kind, reason) VALUES (?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    conn.close()

    store = AccountStore(db)
    events = store.query_events(limit=100)
    types = sorted(e["type"] for e in events)
    assert types == [
        "key_cooldown_cleared",
        "key_disabled",
        "key_disabled",
        "key_enabled",
    ]
    disabled = [e for e in events if e["type"] == "key_disabled"]
    auto = [e for e in disabled if e["data"]["automatic"]]
    assert len(auto) == 1
    assert auto[0]["data"]["account_id"] == "a1"
    store.close()