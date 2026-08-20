"""应用配置（pydantic-settings）。

.env / 环境变量加载；未知字段报错（严格模式），避免拼写错误悄悄失效。
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """全局配置。字段与 .env.example 一一对应。"""

    app_name: str = "opencode-go-pool"
    log_level: str = "INFO"
    host: str = "127.0.0.1"
    port: int = 48700
    # B2：代理上游默认地址与超时
    upstream_base_url: str = "https://api.opencode.ai/v1"
    upstream_timeout: float = 60.0
    # B3：冷却自动扫描与连续失败阈值
    pool_scan_interval_seconds: int = 60
    max_consecutive_failures: int = 3
    # B4：SQLite 状态持久化
    db_path: str = "data/opencode_pool.db"
    # C5：额度查询缓存与超时
    quota_cache_ttl_seconds: int = 60
    quota_timeout_seconds: float = 10.0

    # 严格模式：环境里出现未定义字段时直接报错，防配置漂移
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="forbid",
    )


settings = Settings()
