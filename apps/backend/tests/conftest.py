"""pytest fixtures。"""

import pytest
from fastapi.testclient import TestClient

from opencode_pool.accounts.models import Account
from opencode_pool.accounts.pool import AccountPool
from opencode_pool.app import create_app


@pytest.fixture()
def client() -> TestClient:
    """提供干净的测试客户端（空账号池，无真实配置）。"""
    return TestClient(create_app(config_path=None))


@pytest.fixture()
def client_with_accounts() -> TestClient:
    """带两个账号的测试客户端（config_path 指向不存在的文件 + 注入）。"""
    app = create_app(config_path="__no_such_file__.yaml")
    app.state.account_pool = AccountPool(
        accounts=[
            Account(id="a1", name="A1", api_key="sk-1111"),
            Account(id="a2", name="A2", api_key="sk-2222"),
        ]
    )
    return TestClient(app)
