"""账号池：加载、状态机、脱敏测试。"""

from datetime import datetime, timedelta

from opencode_pool.accounts.loader import load_accounts
from opencode_pool.accounts.models import Account, AccountStatus, mask_api_key
from opencode_pool.accounts.pool import AccountPool


def _fake_now(start: datetime) -> callable:
    """可推进的注入时钟。"""
    current = [start]

    def now() -> datetime:
        return current[0]

    def advance(seconds: float) -> None:
        current[0] = current[0] + timedelta(seconds=seconds)

    now.advance = advance  # type: ignore[attr-defined]
    return now


def _accounts() -> list[Account]:
    return [
        Account(id="a1", name="A1", api_key="sk-11111111"),
        Account(id="a2", name="A2", api_key="sk-22222222"),
        Account(id="a3", name="A3", api_key="sk-33333333", enabled=False),
    ]


# ---- loader ----

def test_load_from_yaml_with_env_refs(tmp_path):
    cfg = tmp_path / "accounts.yaml"
    cfg.write_text(
        "\n".join(
            [
                "accounts:",
                "  - id: a1",
                "    name: One",
                "    api_key: ${OPENCODE_GO_1}",
                "  - id: a2",
                "    name: Two",
                "    api_key: ${OPENCODE_GO_2}",
                "    models: [m1]",
                "    enabled: false",
            ]
        ),
        encoding="utf-8",
    )
    accounts = load_accounts(cfg, env={"OPENCODE_GO_1": "sk-aaa", "OPENCODE_GO_2": "sk-bbb"})
    assert [a.id for a in accounts] == ["a1", "a2"]
    assert accounts[0].api_key == "sk-aaa"
    assert accounts[1].models == ("m1",)
    assert accounts[1].enabled is False


def test_load_missing_env_var_skips_account(tmp_path):
    cfg = tmp_path / "accounts.yaml"
    cfg.write_text(
        "accounts:\n  - id: a1\n    name: One\n    api_key: ${MISSING_VAR}\n",
        encoding="utf-8",
    )
    accounts = load_accounts(cfg, env={})
    assert accounts == []


def test_load_missing_file_returns_empty():
    assert load_accounts("nope/not-exist.yaml", env={}) == []


def test_load_literal_key_allowed(tmp_path):
    """非 ${VAR} 形式的 api_key 按字面处理（本地/测试用）。"""
    cfg = tmp_path / "accounts.yaml"
    cfg.write_text(
        "accounts:\n  - id: a1\n    name: One\n    api_key: sk-literal-key\n",
        encoding="utf-8",
    )
    assert load_accounts(cfg, env={})[0].api_key == "sk-literal-key"


def test_load_json_supported(tmp_path):
    cfg = tmp_path / "accounts.json"
    cfg.write_text(
        '{"accounts": [{"id": "a1", "name": "One", "api_key": "sk-j"}]}',
        encoding="utf-8",
    )
    assert load_accounts(cfg, env={})[0].api_key == "sk-j"


# ---- .env 文件支持 ----

def test_load_key_from_env_file(tmp_path, monkeypatch):
    """api_key 引用的变量可来自 .env 文件（无需进程环境变量）。"""
    monkeypatch.delenv("OPENCODE_GO_KEY_1", raising=False)
    cfg = tmp_path / "accounts.yaml"
    cfg.write_text(
        "accounts:\n  - id: a1\n    name: One\n    api_key: ${OPENCODE_GO_KEY_1}\n",
        encoding="utf-8",
    )
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# 密钥\nOPENCODE_GO_KEY_1=sk-from-dotenv\n",
        encoding="utf-8",
    )
    accounts = load_accounts(cfg, env_file=env_file)
    assert accounts[0].api_key == "sk-from-dotenv"


def test_process_env_overrides_dotenv(tmp_path, monkeypatch):
    """进程环境变量优先于 .env 文件（.env 是默认值）。"""
    monkeypatch.setenv("OPENCODE_GO_KEY_1", "sk-from-process")
    cfg = tmp_path / "accounts.yaml"
    cfg.write_text(
        "accounts:\n  - id: a1\n    name: One\n    api_key: ${OPENCODE_GO_KEY_1}\n",
        encoding="utf-8",
    )
    env_file = tmp_path / ".env"
    env_file.write_text("OPENCODE_GO_KEY_1=sk-from-dotenv\n", encoding="utf-8")
    accounts = load_accounts(cfg, env_file=env_file)
    assert accounts[0].api_key == "sk-from-process"


def test_explicit_env_skips_dotenv(tmp_path):
    """显式传 env（测试注入）时不读 .env——保持确定性。"""
    cfg = tmp_path / "accounts.yaml"
    cfg.write_text(
        "accounts:\n  - id: a1\n    name: One\n    api_key: ${OPENCODE_GO_KEY_1}\n",
        encoding="utf-8",
    )
    env_file = tmp_path / ".env"
    env_file.write_text("OPENCODE_GO_KEY_1=sk-from-dotenv\n", encoding="utf-8")
    # 显式 env（空）→ 引用缺失 → 跳过该账号
    accounts = load_accounts(cfg, env={}, env_file=env_file)
    assert accounts == []


def test_env_file_quotes_and_comments(tmp_path):
    """.env 解析：引号去除、注释与空行忽略。"""
    from opencode_pool.accounts.loader import _parse_env_file

    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n# comment\nA=plain\nB='quoted'\nC=\"dq\"\nBAD LINE\nD=\n",
        encoding="utf-8",
    )
    parsed = _parse_env_file(env_file)
    assert parsed == {"A": "plain", "B": "quoted", "C": "dq", "D": ""}


def test_missing_env_file_is_noop(tmp_path):
    from opencode_pool.accounts.loader import _parse_env_file

    assert _parse_env_file(tmp_path / "nope.env") == {}


# ---- 状态机 ----

def test_initial_status_healthy():
    pool = AccountPool(accounts=_accounts(), now=_fake_now(datetime(2026, 1, 1)))
    assert pool.pick_next().id == "a1"


def test_mark_down_moves_to_cooldown_and_skipped():
    now = _fake_now(datetime(2026, 1, 1))
    pool = AccountPool(accounts=_accounts(), now=now)
    assert pool.mark_down("a1", "quota exhausted") is True
    a1 = pool.account("a1")
    assert a1.status == AccountStatus.COOLDOWN
    assert a1.error_count == 1
    assert a1.last_error == "quota exhausted"
    # pick 跳过 a1，选 a2（a3 disabled）
    assert pool.pick_next().id == "a2"


def test_cooldown_expires_and_recovers():
    now = _fake_now(datetime(2026, 1, 1))
    pool = AccountPool(accounts=_accounts(), now=now)
    pool.mark_down("a1", "quota")
    now.advance(pool._cooldown_seconds + 1)
    picked = pool.pick_next()
    assert picked.id == "a1"
    assert pool.account("a1").status == AccountStatus.HEALTHY


def test_disable_skips_account():
    pool = AccountPool(accounts=_accounts(), now=_fake_now(datetime(2026, 1, 1)))
    assert pool.disable("a2", "manual") is True
    assert pool.pick_next().id == "a1"


def test_enable_restores_healthy():
    pool = AccountPool(accounts=_accounts(), now=_fake_now(datetime(2026, 1, 1)))
    pool.disable("a2", "manual")
    pool.clear_account("a2")
    assert pool.enable("a2") is True
    assert pool.pick_next().id == "a1"  # a1 仍在最前
    assert pool.account("a2").status == AccountStatus.HEALTHY


def test_disable_during_cooldown_keeps_disabled_precedence():
    now = _fake_now(datetime(2026, 1, 1))
    pool = AccountPool(accounts=_accounts(), now=now)
    pool.mark_down("a1", "quota")
    assert pool.disable("a1", "manual") is True
    # 即使 cooldown 到期，disabled 仍不参与 pick
    now.advance(pool._cooldown_seconds + 10)
    assert pool.pick_next().id == "a2"


def test_mark_down_absent_account_returns_false():
    pool = AccountPool(accounts=_accounts(), now=_fake_now(datetime(2026, 1, 1)))
    assert pool.mark_down("nope", "x") is False


def test_clear_restores_healthy():
    now = _fake_now(datetime(2026, 1, 1))
    pool = AccountPool(accounts=_accounts(), now=now)
    pool.mark_down("a1", "quota")
    assert pool.clear_account("a1") is True
    assert pool.account("a1").status == AccountStatus.HEALTHY
    assert pool.account("a1").error_count == 0


# ---- 脱敏 ----

def test_mask_api_key():
    assert mask_api_key("") == ""
    # sk-1234567890abcd 长度 17 → 13 星 + 末4
    assert mask_api_key("sk-1234567890abcd") == "*************abcd"
    assert mask_api_key("abcd") == "****"


def test_public_view_no_api_key():
    pool = AccountPool(accounts=_accounts(), now=_fake_now(datetime(2026, 1, 1)))
    view = pool.public_views()[0]
    assert "api_key" not in view
    assert view["id"] == "a1"
    assert view["status"] == "healthy"


def test_public_view_hides_api_key_even_after_changes():
    now = _fake_now(datetime(2026, 1, 1))
    pool = AccountPool(accounts=_accounts(), now=now)
    pool.mark_down("a1", "quota")
    view = pool.account("a1").public_view()
    assert "api_key" not in view
    assert view["status"] == "cooldown"
    assert view["last_error"] == "quota"
