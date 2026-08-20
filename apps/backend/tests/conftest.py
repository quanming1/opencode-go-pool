"""pytest fixtures。

隔离原则：所有 fixture 都用 tmp_path 隔离 DB 与账号配置，
绝不触碰本地真实 config/accounts.yaml 与 data/opencode_pool.db
（否则测试会读到生产数据且污染生产统计）。
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from opencode_pool.accounts.models import Account
from opencode_pool.accounts.pool import AccountPool
from opencode_pool.app import create_app
from opencode_pool.config import settings


@pytest.fixture()
def client(tmp_path, monkeypatch) -> TestClient:
    """干净的测试客户端：不存在的账号配置 + 临时 DB（空账号池）。"""
    monkeypatch.setattr(settings, "db_path", str(tmp_path / "test.db"))
    return TestClient(create_app(config_path=str(tmp_path / "no-accounts.yaml")))


@pytest.fixture()
def client_with_accounts(tmp_path, monkeypatch) -> TestClient:
    """带两个账号的测试客户端（配置指向不存在文件 + 手动注入账号 + 临时 DB）。"""
    monkeypatch.setattr(settings, "db_path", str(tmp_path / "test.db"))
    app = create_app(config_path=str(tmp_path / "no-accounts.yaml"))
    app.state.account_pool = AccountPool(
        accounts=[
            Account(id="a1", name="A1", api_key="sk-1111"),
            Account(id="a2", name="A2", api_key="sk-2222"),
        ]
    )
    return TestClient(app)


@pytest.fixture()
def temp_db_path(tmp_path) -> str:
    """临时 SQLite 路径（供需要直接操作 store 的测试用）。"""
    return str(Path(tmp_path) / "pool.db")
