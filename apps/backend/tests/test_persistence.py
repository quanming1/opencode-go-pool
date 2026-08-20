"""账号池持久化集成测试（B4）：跨实例恢复状态。"""

from datetime import datetime, timedelta

from opencode_pool.accounts.models import Account, AccountStatus
from opencode_pool.accounts.pool import AccountPool
from opencode_pool.store.sqlite_store import AccountStore


def _fake_now(start: datetime):
    current = [start]

    def now() -> datetime:
        return current[0]

    def advance(seconds: float) -> None:
        current[0] = current[0] + timedelta(seconds=seconds)

    now.advance = advance  # type: ignore[attr-defined]
    return now


def _accounts() -> list[Account]:
    return [
        Account(id="a1", name="A1", api_key="sk-1111"),
        Account(id="a2", name="A2", api_key="sk-2222"),
    ]


def test_restore_keeps_cooldown(tmp_path):
    """重启后未到期的 cooldown 保留。"""
    db = str(tmp_path / "pool.db")
    now = _fake_now(datetime(2026, 1, 1))

    # 实例 A：冷却 a1（TTL 大，未到期）
    store_a = AccountStore(db)
    pool_a = AccountPool(accounts=_accounts(), now=now, store=store_a)
    pool_a.mark_down("a1", "quota", retry_after=3600)
    assert pool_a.account("a1").status == AccountStatus.COOLDOWN
    store_a.close()

    # 实例 B（模拟重启）：新 pool + 同一 db
    store_b = AccountStore(db)
    pool_b = AccountPool(accounts=_accounts(), now=now, store=store_b)
    pool_b.restore_from_store()
    assert pool_b.account("a1").status == AccountStatus.COOLDOWN
    assert pool_b.account("a1").consecutive_failures == 1
    assert pool_b.account("a2").status == AccountStatus.HEALTHY
    store_b.close()


def test_restore_expired_cooldown_becomes_healthy(tmp_path):
    """重启时 cooldown 已到期 → 恢复 healthy。"""
    db = str(tmp_path / "expired.db")
    now = _fake_now(datetime(2026, 1, 1))

    store_a = AccountStore(db)
    pool_a = AccountPool(accounts=_accounts(), now=now, store=store_a)
    pool_a.mark_down("a1", "quota", retry_after=10)
    store_a.close()

    # 推进时间后再"重启"
    now2 = _fake_now(datetime(2026, 1, 1, 0, 1, 0))  # 60s 后
    store_b = AccountStore(db)
    pool_b = AccountPool(accounts=_accounts(), now=now2, store=store_b)
    pool_b.restore_from_store()
    assert pool_b.account("a1").status == AccountStatus.HEALTHY
    store_b.close()


def test_restore_keeps_disabled(tmp_path):
    """禁用账号重启后仍禁用。"""
    db = str(tmp_path / "disabled.db")
    now = _fake_now(datetime(2026, 1, 1))

    store_a = AccountStore(db)
    pool_a = AccountPool(accounts=_accounts(), now=now, store=store_a)
    pool_a.disable("a2", "manual")
    store_a.close()

    store_b = AccountStore(db)
    pool_b = AccountPool(accounts=_accounts(), now=now, store=store_b)
    pool_b.restore_from_store()
    assert pool_b.account("a2").status == AccountStatus.DISABLED
    assert pool_b.account("a2").enabled is False
    assert pool_b.pick_next().id == "a1"  # a2 不参与 pick
    store_b.close()


def test_persist_on_state_changes(tmp_path):
    """各状态变更后 DB 与内存一致。"""
    db = str(tmp_path / "changes.db")
    now = _fake_now(datetime(2026, 1, 1))
    store = AccountStore(db)
    pool = AccountPool(accounts=_accounts(), now=now, store=store)

    pool.mark_down("a1", "quota")
    state = store.load_accounts_state()
    assert state["a1"]["status"] == "cooldown"

    pool.clear_account("a1")
    state = store.load_accounts_state()
    assert state["a1"]["status"] == "healthy"
    assert state["a1"]["consecutive_failures"] == 0

    pool.disable("a2", "manual")
    state = store.load_accounts_state()
    assert state["a2"]["enabled"] is False

    pool.enable("a2")
    state = store.load_accounts_state()
    assert state["a2"]["status"] == "healthy"
    store.close()


def test_record_success_persists_reset(tmp_path):
    db = str(tmp_path / "success.db")
    now = _fake_now(datetime(2026, 1, 1))
    store = AccountStore(db)
    pool = AccountPool(accounts=_accounts(), now=now, store=store, max_consecutive_failures=5)

    pool.mark_down("a1", "x")
    pool.mark_down("a1", "x")
    pool.record_success("a1")
    state = store.load_accounts_state()
    assert state["a1"]["consecutive_failures"] == 0
    store.close()


def test_history_restored_from_db(tmp_path):
    """切换历史在重启后仍可读取（通过 store 的 load_history 校验）。"""
    db = str(tmp_path / "history.db")
    now = _fake_now(datetime(2026, 1, 1))
    store_a = AccountStore(db)
    pool_a = AccountPool(accounts=_accounts(), now=now, store=store_a)
    pool_a.mark_down("a1", "quota", kind="quota")
    pool_a.disable("a2", "manual")
    store_a.close()

    store_b = AccountStore(db)
    hist = store_b.load_history()
    kinds = [h["kind"] for h in hist]
    assert kinds == ["disable", "quota"]
    store_b.close()
