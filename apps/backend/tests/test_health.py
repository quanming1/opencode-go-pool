"""健康检查与配置加载测试。"""

import pytest

from opencode_pool import __version__
from opencode_pool.config import Settings


def test_health_returns_ok_with_version(client):
    """AC1 核心：/health 返回 200 且 body 含 status/version。"""
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["version"] == __version__


def test_settings_defaults():
    """配置默认值与 .env.example 一致。"""
    settings = Settings(_env_file=None)
    assert settings.app_name == "opencode-go-pool"
    assert settings.log_level == "INFO"
    assert settings.host == "127.0.0.1"
    assert settings.port == 48700


def test_settings_env_override(monkeypatch):
    """环境变量可覆盖默认值。"""
    monkeypatch.setenv("PORT", "9000")
    settings = Settings(_env_file=None)
    assert settings.port == 9000


def test_settings_rejects_unknown_field_in_env_file(tmp_path, monkeypatch):
    """严格模式：.env 文件中出现未定义字段直接报错（防拼写错误）。

    注意：extra="forbid" 约束的是 .env 文件里的字段；系统环境变量
    （PATH 等海量无关变量）不参与校验，这是 pydantic-settings 的默认语义。
    """
    env_file = tmp_path / ".env"
    env_file.write_text("APP_NAME=ok\nUNKNOWN_FIELD=x\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    try:
        Settings(_env_file=env_file)
    except Exception:  # pydantic ValidationError
        return
    pytest.fail(".env 中未知字段应当触发校验错误")


def test_app_title():
    """应用元信息可读。"""
    from opencode_pool.app import app

    assert app.title == "OpenCode Go Pool"
