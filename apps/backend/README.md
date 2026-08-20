# OpenCode Go Pool — 后端

FastAPI 代理核心：账号池管理、Responses 协议透明转发、额度错误识别与自动切换、状态持久化、用量统计。

## 模块一览

| 模块 | 路径 | 职责 |
|---|---|---|
| accounts | `src/opencode_pool/accounts/` | 账号数据模型、配置加载（YAML/JSON + `${ENV_VAR}` 引用）、账号池状态机（healthy/cooldown/disabled、连续失败阈值、切换历史） |
| proxy | `src/opencode_pool/proxy/` | Responses 透明转发（非流式 JSON / 流式 SSE）、错误分类（quota/auth/bad_request/server/network）、失败切换与 Retry-After 动态冷却 |
| usage | `src/opencode_pool/usage/` | 转发用量记录（请求数/token）、统计聚合、切换历史查询（中文语义标签） |
| store | `src/opencode_pool/store/` | SQLite 持久化：账号运行时状态、切换历史、用量事件（DB 不可写自动降级纯内存） |
| scheduler | `src/opencode_pool/scheduler.py` | 后台冷却扫描（周期恢复到期账号，随应用 lifespan 启停） |
| api | `src/opencode_pool/api/` | HTTP 路由：`/api/accounts`（脱敏视图）、`/api/stats`、`/api/switch-history` |
| config | `src/opencode_pool/config.py` | pydantic-settings 配置（env + .env，严格模式拒绝未知字段） |

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

## SQLite 数据说明

- 默认路径：`data/opencode_pool.db`（`DB_PATH` 可覆盖；目录自动创建；已 gitignore）。
- 三张表：
  - `accounts`：账号运行时状态（status / cooldown_until / consecutive_failures / enabled 等），重启自动恢复（到期冷却按当前时间懒恢复）；
  - `switch_history`：账号切换事件（最近 100 条，环形裁剪）；
  - `usage_events`：转发用量事件（最近 2000 条，含 success/error 分类与 token 数）。
- DB 不可写（路径只读等）时服务可启动，退化为纯内存（日志有警告）。

## 账号配置

见 `config/accounts.example.yaml`——`api_key` 用 `${OPENCODE_GO_KEY_1}` 形式引用环境变量，真实密钥绝不入库。完整使用流程见 [docs/usage.md](../../docs/usage.md)。

## 环境变量

见 `.env.example`（复制为 `.env` 使用；`.env` 不入库）。
