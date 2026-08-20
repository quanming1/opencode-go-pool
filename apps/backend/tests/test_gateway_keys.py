"""C3 网关 key 管理与鉴权测试。"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from opencode_pool.accounts.models import Account
from opencode_pool.accounts.pool import AccountPool
from opencode_pool.auth.gateway_key import KeyManager
from opencode_pool.proxy.router import router as proxy_router
from opencode_pool.store.sqlite_store import AccountStore


@pytest.fixture()
def key_app(tmp_path):
    """带真实 KeyManager 的测试 app。"""
    store = AccountStore(str(tmp_path / "keys.db"))
    pool = AccountPool(accounts=[Account(id="a1", name="A", api_key="sk-1111")], store=store)
    manager = KeyManager(store, master_key="")

    app = FastAPI()
    app.state.account_pool = pool
    app.state.key_manager = manager
    from opencode_pool.api.keys import router as keys_router

    app.include_router(keys_router)
    app.include_router(proxy_router)
    return app, manager, store


def test_no_keys_no_master_auth_disabled(key_app):
    """兼容模式：无 key 且无 master → 转发放行。"""
    app, _, _ = key_app

    class MockForwarder:
        async def forward(self, request, upstream_path="/responses"):
            from fastapi import Response

            return Response(content='{"ok":1}', media_type="application/json")

        async def list_models(self):
            return {"object": "list", "data": []}

    app.state.forwarder = MockForwarder()
    client = TestClient(app)
    resp = client.get("/api/v1/models")
    assert resp.status_code == 200


def test_key_created_verified_revoked(key_app):
    """key 生成 → 校验通过 → 吊销 → 校验失败。"""
    _, manager, _ = key_app
    created = manager.create_key("test")
    assert created is not None
    raw = created["key"]
    assert raw.startswith("gk-")
    assert manager.verify(raw)
    assert manager.revoke_key(created["id"])
    assert not manager.verify(raw)


def test_master_key_verifies(key_app):
    """master key 与库内 key 等效。"""
    store = AccountStore(":memory:")
    manager = KeyManager(store, master_key="master-secret")
    assert manager.verify("master-secret")
    assert not manager.verify("wrong")
    store.close()


def test_auth_enabled_logic(tmp_path):
    store = AccountStore(str(tmp_path / "e.db"))
    manager = KeyManager(store)
    assert not manager.auth_enabled()
    manager.create_key("x")
    assert manager.auth_enabled()
    store.close()


def test_keys_api_crud(key_app):
    """POST/GET/DELETE /api/keys 全流程。

    语义：生成第一个 key 前管理端点放行（首次配置）；
    生成后鉴权激活，后续管理请求必须带有效 Bearer。
    """
    app, manager, _ = key_app
    client = TestClient(app)

    # 空 key 配置（无 master）→ 管理端点放行（首次配置语义）
    resp = client.post("/api/keys", json={"label": "ftre"})
    assert resp.status_code == 201
    created = resp.json()
    assert created["key"].startswith("gk-")

    auth = {"Authorization": f"Bearer {created['key']}"}
    resp = client.get("/api/keys", headers=auth)
    keys = resp.json()["keys"]
    assert len(keys) == 1
    assert keys[0]["label"] == "ftre"
    assert "key" not in keys[0]  # 列表不返回明文/哈希

    # 无鉴权头的请求在激活后被拒
    assert client.get("/api/keys").status_code == 401

    resp = client.delete(f"/api/keys/{created['id']}", headers=auth)
    assert resp.json()["ok"] is True
    # 吊销后该 key 立即失效（无 master key 时管理端点随之锁死，
    # 需配 GATEWAY_MASTER_KEY 或清库解锁——预期边界行为）
    assert client.get("/api/keys", headers=auth).status_code == 401


def test_forward_401_after_key_exists(key_app):
    """存在有效 key 后：无 Bearer → 401；带有效 key → 通过鉴权（转发 mock）。"""
    app, manager, _ = key_app
    created = manager.create_key("t")
    assert created is not None

    # 注入 mock forwarder（鉴权在路由依赖层，先于 forwarder 生效）
    class MockForwarder:
        async def forward(self, request, upstream_path="/responses"):
            from fastapi import Response

            return Response(content='{"ok":1}', media_type="application/json")

        async def list_models(self):
            return {"object": "list", "data": []}

    app.state.forwarder = MockForwarder()
    client = TestClient(app)

    # 无鉴权头 → 401
    resp = client.get("/api/v1/models")
    assert resp.status_code == 401

    # 错误 key → 401
    resp = client.get("/api/v1/models", headers={"Authorization": "Bearer gk-wrong"})
    assert resp.status_code == 401

    # 有效 key → 200
    resp = client.get("/api/v1/models", headers={"Authorization": f"Bearer {created['key']}"})
    assert resp.status_code == 200

    # 吊销后 → 401
    manager.revoke_key(created["id"])
    resp = client.get("/api/v1/models", headers={"Authorization": f"Bearer {created['key']}"})
    assert resp.status_code == 401


def test_account_control_endpoints(tmp_path, monkeypatch):
    """账号控制 API：clear/enable/disable 生效且池状态正确。"""
    from opencode_pool.api.accounts import router as accounts_router

    store = AccountStore(str(tmp_path / "ctl.db"))
    pool = AccountPool(
        accounts=[Account(id="a1", name="A", api_key="sk-1111")], store=store
    )
    manager = KeyManager(store)  # 无 key → 管理端点放行（兼容模式）

    app = FastAPI()
    app.state.account_pool = pool
    app.state.key_manager = manager
    app.include_router(accounts_router)
    client = TestClient(app)

    # 制造冷却
    pool.mark_down("a1", "test")
    assert pool.account("a1").status.value == "cooldown"

    # clear → healthy
    resp = client.post("/api/accounts/a1/clear")
    assert resp.json() == {"ok": True, "status": "healthy"}

    # disable → disabled 且不参与 pick
    resp = client.post("/api/accounts/a1/disable")
    assert resp.json()["status"] == "disabled"
    assert pool.pick_next() is None

    # enable → healthy
    resp = client.post("/api/accounts/a1/enable")
    assert resp.json()["status"] == "healthy"
    assert pool.pick_next() is not None

    # 不存在的账号
    resp = client.post("/api/accounts/nope/clear")
    assert resp.json()["ok"] is False
    store.close()
