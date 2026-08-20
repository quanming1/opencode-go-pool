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


def test_write_event_and_history(tmp_path):
    db = tmp_path / "hist.db"
    store = AccountStore(str(db))
    store.write_event("2026-08-19T00:00:00", "a1", "quota", "rate limit")
    store.write_event("2026-08-19T00:00:01", "a1", "recover", "cooldown expired")

    hist = store.load_history()
    # 新在前
    assert hist[0]["kind"] == "recover"
    assert hist[1]["kind"] == "quota"
    assert hist[1]["account_id"] == "a1"
    store.close()


def test_history_trimmed_to_limit(tmp_path):
    db = tmp_path / "trim.db"
    store = AccountStore(str(db), history_limit=3)
    for i in range(5):
        store.write_event(f"t{i}", "a1", "error", f"e{i}")
    hist = store.load_history()
    assert len(hist) == 3
    assert hist[0]["reason"] == "e4"
    assert hist[-1]["reason"] == "e2"
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
