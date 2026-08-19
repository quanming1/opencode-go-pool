"""pytest fixtures。"""

import pytest
from fastapi.testclient import TestClient

from opencode_pool.app import create_app


@pytest.fixture()
def client() -> TestClient:
    """提供干净的测试客户端。"""
    return TestClient(create_app())
