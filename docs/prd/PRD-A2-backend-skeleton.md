# PRD-A2-后端FastAPI骨架

> 状态生命周期：草稿 → 评审 → approved（定稿）→ 开发中 → 已验收

## 元信息

| 字段 | 值 |
|---|---|
| 阶段 | A2 |
| 名称 | 后端 FastAPI 骨架 |
| 状态 | 已验收 |
| 创建日期 | 2026-08-19 |
| 定稿日期 | 2026-08-19 |
| 验收日期 | 2026-08-19 |
| 关联文档 | docs/TODO.yaml 阶段 A2 |

## 1. 背景与目标

- **背景**：代理核心（B 阶段）需要 FastAPI 后端承载账号池、转发、切换逻辑。A2 先搭可运行的后端骨架：项目结构、配置加载、健康检查、测试与 lint 基架。
- **目标**：`apps/backend/` 是一个可启动的 FastAPI 服务（uvicorn 运行、/health 返回 200），pytest + ruff 通过。
- **非目标**：不实现账号池、代理转发、切换逻辑（B 阶段）；不接数据库（B4）；不做 Docker（G1 时再议）；不实现鉴权。

## 2. 需求范围

### 2.1 功能需求

- [ ] FR1：项目结构 `apps/backend/`：`src/opencode_pool/`（包）+ `tests/` + `pyproject.toml` + `.env.example`。
- [ ] FR2：FastAPI 应用工厂 + `/health` 端点返回 `{"status": "ok", "version": <版本号>}`，版本号从包元数据读取。
- [ ] FR3：配置加载：环境变量 + `.env`（pydantic-settings），含 APP_NAME、APP_VERSION、LOG_LEVEL；未知字段报错（严格模式）。
- [ ] FR4：logging 统一配置（logging 模块），请求日志格式含时间与级别。
- [ ] FR5：pyproject.toml 声明依赖：fastapi、uvicorn、pydantic-settings、pytest、httpx、ruff（dev）；版本号 0.1.0。
- [ ] FR6：tests/ 含 /health 与配置加载测试（TestClient）；测试不依赖真实网络。

### 2.2 非功能需求

- 性能：骨架阶段无硬性指标；/health 响应 < 50ms（本地）。
- 安全：.env 不提交（.gitignore 已排除）；.env.example 只含占位符。
- 兼容性：Python 3.12；Windows / Linux 可运行。

## 3. 技术方案

- 包结构：

```
apps/backend/
├─ pyproject.toml
├─ .env.example
├─ src/opencode_pool/
│  ├─ __init__.py        # __version__
│  ├─ config.py          # Settings（pydantic-settings）
│  ├─ logging_setup.py   # 统一日志
│  └─ app.py             # create_app() 工厂 + /health
└─ tests/
   ├─ conftest.py
   └─ test_health.py
```

- 依赖：fastapi（Web 框架）、uvicorn（ASGI server）、pydantic-settings（配置）、pytest/httpx（测试）、ruff（lint）。
- 启动：`uvicorn opencode_pool.app:app --host 127.0.0.1 --port 48700`（48700 为项目默认端口，避免与 ftre 48650 冲突）。

## 4. 接口定义

- `GET /health` → 200 `{"status": "ok", "version": "0.1.0"}`
- 配置结构（.env）：`APP_NAME=opencode-go-pool`、`LOG_LEVEL=INFO`。

## 5. 验收标准

- [ ] AC1：`cd apps/backend && python -m pytest` 全绿（含 /health 与配置测试）。
- [ ] AC2：`cd apps/backend && ruff check src tests` 无警告。
- [ ] AC3：本地启动 uvicorn 后 `GET /health` 返回 200 且 body 含 version。
- [ ] AC4：.env.example 存在且无真实密钥；.env 不入库（git status 干净）。

## 6. 测试计划

- 单元：/health 状态码与 body；配置默认值与 env 覆盖；未知配置字段报错。
- 手动：uvicorn 启动 + curl /health。

## 7. 里程碑与估算

| 子任务 | 预估 |
|---|---|
| 包结构与依赖 | 10 分钟 |
| 配置 + 日志 + 应用工厂 | 20 分钟 |
| 测试 + lint 通过 | 15 分钟 |

## 8. 风险与对策

| 风险 | 对策 |
|---|---|
| pydantic-settings 版本差异 | 锁在 pyproject 声明版本范围，CI 前本地验证 |
| 端口冲突 | 默认 48700，可经 env 覆盖 |

## 9. 变更记录

| 日期 | 变更内容 | 理由 |
|---|---|---|
| 2026-08-19 | 初始定稿 | — |
| 2026-08-19 | 验收通过：pytest 5 passed、ruff 无警告、/health 实测 200 | 阶段 A2 完成 |
