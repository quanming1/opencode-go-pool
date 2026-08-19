"""账号 API 集成测试。"""


def test_accounts_empty_pool(client):
    """AC6：无配置时可启动且 /api/accounts 返回空列表。"""
    resp = client.get("/api/accounts")
    assert resp.status_code == 200
    assert resp.json() == {"accounts": []}


def test_accounts_returns_sanitized_views(client_with_accounts):
    """AC5：返回脱敏视图，不含 api_key。"""
    resp = client_with_accounts.get("/api/accounts")
    assert resp.status_code == 200
    accounts = resp.json()["accounts"]
    assert [a["id"] for a in accounts] == ["a1", "a2"]
    for a in accounts:
        assert "api_key" not in a
        assert a["status"] == "healthy"
        assert a["cooldown_until"] is None
        assert a["error_count"] == 0


def test_accounts_reflect_state_change(client_with_accounts):
    """状态流转后 API 反映最新状态。"""
    pool = client_with_accounts.app.state.account_pool
    pool.mark_down("a1", "quota exhausted")
    resp = client_with_accounts.get("/api/accounts")
    by_id = {a["id"]: a for a in resp.json()["accounts"]}
    assert by_id["a1"]["status"] == "cooldown"
    assert by_id["a1"]["last_error"] == "quota exhausted"
    assert by_id["a1"]["error_count"] == 1
    assert by_id["a2"]["status"] == "healthy"
