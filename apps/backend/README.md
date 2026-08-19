# OpenCode Go Pool — 后端

FastAPI 代理核心：账号池管理、Responses 协议透明转发、额度错误识别与自动切换、状态持久化。

## 启动

```bash
cd apps/backend
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -e ".[dev]"
uvicorn opencode_pool.app:app --host 127.0.0.1 --port 48700
```

健康检查：`GET http://127.0.0.1:48700/health`

## 测试与 lint

```bash
pytest
ruff check src tests
```

## 环境变量

见 `.env.example`（复制为 `.env` 使用；`.env` 不入库）。
