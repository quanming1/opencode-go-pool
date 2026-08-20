"""SQLite 存储层单测（B4）。"""

from pathlib import Path

from opencode_pool.accounts.models import Account, AccountStatus
from opencode_pool.store.sqlite_store import AccountStore


def _account(**kwargs) -> Account:
    base = dict(id="a1", name="A1", api_key="sk-1111")
    base.update(kwargs)
    return Account(**base)


def test_save_and_load_state(tmp_path):
    db = tmp_path / "pool.db"
    store = AccountStore(str(db))
    assert store.available

    a1 = _account()
    a1.status = AccountStatus.COOLDOWN
    a1.consecutive_failures = 2
    a1.error_count = 3
    store.save_state(a1)

    loaded = store.load_accounts_state()
    assert "a1" in loaded
    st = loaded["a1"]
    assert st["status"] == "cooldown"
    assert st["consecutive_failures"] == 2
    assert st["error_count"] == 3
    assert st["enabled"] is True
    store.close()


def test_empty_store_returns_empty(tmp_path):
    store = AccountStore(str(tmp_path / "empty.db"))
    assert store.load_accounts_state() == {}
    store.close()


def test_save_and_query_events(tmp_path):
    """C4：save_event 落库后 query_events 可读（新在前）。"""
    db = tmp_path / "hist.db"
    store = AccountStore(str(db))
    store.save_event("key_cooldown_started", "2026-08-19T00:00:00", '{"a":1}', '{"s":1}')
    store.save_event("key_cooldown_completed", "2026-08-19T00:00:01", '{"a":2}', '{"s":1}')

    rows = store.query_events(limit=10)
    assert [r["type"] for r in rows] == ["key_cooldown_completed", "key_cooldown_started"]
    assert rows[0]["data"] == {"a": 2}
    assert rows[1]["event_time"] == "2026-08-19T00:00:00"
    store.close()


def test_events_trimmed_to_limit(tmp_path):
    """C4：events 裁剪到 event_limit。"""
    db = tmp_path / "trim.db"
    store = AccountStore(str(db), event_limit=3)
    for i in range(5):
        store.save_event("key_enabled", f"t{i}", f'{{"i":{i}}}', "{}")
    rows = store.query_events(limit=10)
    assert len(rows) == 3
    assert rows[0]["data"] == {"i": 4}
    assert rows[-1]["data"] == {"i": 2}
    store.close()


def test_unwritable_path_degrades(tmp_path):
    """DB 路径不可写（父目录不存在且无法创建）→ available=False，不抛。"""
    bad = Path(tmp_path) / "no_dir" / "x" / "pool.db"
    # 故意创建一个文件占位，阻止 mkdir 父目录成功（Windows 下最易复现的不可写）
    blocker = Path(tmp_path) / "no_dir"
    blocker.mkdir()
    (blocker / "x").write_text("not-a-dir-file", encoding="utf-8")

    store = AccountStore(str(bad))
    assert store.available is False
    # 降级后 save/load 不抛
    store.save_state(_account())
    assert store.load_accounts_state() == {}
    store.close()
