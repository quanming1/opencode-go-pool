"""轮换强化（B3）测试：自动恢复、连续失败阈值、Retry-After、切换历史。"""

from datetime import datetime, timedelta

from opencode_pool.accounts.models import Account
from opencode_pool.accounts.pool import AccountPool


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


# ---- 主动扫描恢复 ----

def test_scan_cooldowns_recovers_expired():
    now = _fake_now(datetime(2026, 1, 1))
    pool = AccountPool(accounts=_accounts(), now=now, cooldown_seconds=100)
    pool.mark_down("a1", "quota")
    assert pool.account("a1").status.value == "cooldown"

    now.advance(101)
    assert pool.scan_cooldowns() == 1
    assert pool.account("a1").status.value == "healthy"
    assert pool.account("a1").consecutive_failures == 0


def test_scan_cooldowns_skips_not_expired():
    now = _fake_now(datetime(2026, 1, 1))
    pool = AccountPool(accounts=_accounts(), now=now, cooldown_seconds=100)
    pool.mark_down("a1", "quota")
    now.advance(50)
    assert pool.scan_cooldowns() == 0
    assert pool.account("a1").status.value == "cooldown"


# ---- Retry-After ----

def test_mark_down_with_retry_after():
    now = _fake_now(datetime(2026, 1, 1))
    pool = AccountPool(accounts=_accounts(), now=now, cooldown_seconds=100)
    pool.mark_down("a1", "quota", retry_after=30)
    assert pool.account("a1").cooldown_until == datetime(2026, 1, 1, 0, 0, 30)


def test_mark_down_default_ttl_without_retry_after():
    now = _fake_now(datetime(2026, 1, 1))
    pool = AccountPool(accounts=_accounts(), now=now, cooldown_seconds=100)
    pool.mark_down("a1", "quota")
    assert pool.account("a1").cooldown_until == datetime(2026, 1, 1, 0, 1, 40)


# ---- 连续失败阈值 ----

def test_consecutive_failures_auto_disable():
    now = _fake_now(datetime(2026, 1, 1))
    pool = AccountPool(accounts=_accounts(), now=now, max_consecutive_failures=3)
    for _ in range(3):
        pool.mark_down("a1", "quota")
    a1 = pool.account("a1")
    assert a1.status.value == "disabled"
    assert a1.consecutive_failures == 3
    assert "auto-disabled" in (a1.last_error or "")


def test_auto_disabled_not_picked():
    now = _fake_now(datetime(2026, 1, 1))
    pool = AccountPool(accounts=_accounts(), now=now, max_consecutive_failures=2)
    pool.mark_down("a1", "quota")
    pool.mark_down("a1", "quota")
    # a1 被自动禁用，a2 仍可 pick
    assert pool.pick_next().id == "a2"


def test_record_success_resets_consecutive_failures():
    now = _fake_now(datetime(2026, 1, 1))
    pool = AccountPool(accounts=_accounts(), now=now, max_consecutive_failures=5)
    pool.mark_down("a1", "x")
    pool.mark_down("a1", "x")
    assert pool.account("a1").consecutive_failures == 2
    pool.record_success("a1")
    assert pool.account("a1").consecutive_failures == 0
    # 累计 error_count 保留
    assert pool.account("a1").error_count == 2


def test_clear_account_resets_consecutive_failures():
    now = _fake_now(datetime(2026, 1, 1))
    pool = AccountPool(accounts=_accounts(), now=now)
    pool.mark_down("a1", "x")
    pool.clear_account("a1")
    assert pool.account("a1").consecutive_failures == 0
    assert pool.account("a1").status.value == "healthy"


# ---- 切换历史 ----

def test_switch_history_records_events():
    now = _fake_now(datetime(2026, 1, 1))
    pool = AccountPool(accounts=_accounts(), now=now, history_limit=5)
    pool.mark_down("a1", "quota", kind="quota")
    pool.disable("a2", "manual")
    pool.enable("a2")
    hist = pool.switch_history()
    kinds = [e["kind"] for e in hist]
    assert kinds == ["enable", "disable", "quota"]
    # 最新在前
    assert hist[0]["kind"] == "enable"
    assert hist[0]["account_id"] == "a2"


def test_switch_history_ring_buffer_limit():
    now = _fake_now(datetime(2026, 1, 1))
    pool = AccountPool(accounts=_accounts(), now=now, history_limit=3, max_consecutive_failures=10)
    for i in range(5):
        pool.mark_down("a1", f"e{i}", kind="error")
    hist = pool.switch_history()
    assert len(hist) == 3
    # 环形保留最近 3 条
    assert hist[0]["reason"] == "e4"
    assert hist[2]["reason"] == "e2"


# ---- public_view 扩展 ----

def test_public_view_has_new_fields():
    now = _fake_now(datetime(2026, 1, 1))
    pool = AccountPool(accounts=_accounts(), now=now)
    pool.mark_down("a1", "quota", retry_after=60)
    view = pool.account("a1").public_view()
    assert view["consecutive_failures"] == 1
    assert view["cooldown_seconds_remaining"] is not None
    assert view["cooldown_seconds_remaining"] >= 0 or view["cooldown_seconds_remaining"] is None


# ---- Forwarder 透传 Retry-After ----

def test_upstream_error_parser():
    from opencode_pool.proxy.forwarder import _parse_retry_after

    assert _parse_retry_after("30") == 30
    assert _parse_retry_after(" 5 ") == 5
    assert _parse_retry_after("Wed, 21 Oct 2026 07:28:00 GMT") is None
    assert _parse_retry_after(None) is None
    assert _parse_retry_after("abc") is None


def test_upstream_error_holds_retry_after():
    import opencode_pool.proxy.errors as errors

    e = errors.UpstreamError(
        errors.ErrorKind.QUOTA, status=429, detail="rate limit", retry_after=45
    )
    assert e.retry_after == 45
    assert e.kind == errors.ErrorKind.QUOTA
