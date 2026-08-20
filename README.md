# OpenCode Go Pool

多个 OpenCode Go 订阅账号合并为一个逻辑上游的代理服务 + 可视化监控台。

## 解决什么问题

单个 OpenCode Go 账号有 5 小时调用窗口限制，不够用时把多个订阅账号组成一个池子：某账号额度耗尽（429/限流）自动冷却并切换到下一个账号，对客户端呈现为一个统一 API 入口。配套 Web 大盘实时查看账号状态、用量趋势与切换历史。

## 架构

```
客户端（ftre / 任意 OpenAI Responses 调用方）
        ↓  OpenAI Responses 协议
  OpenCode Go Pool 代理（FastAPI :48700）
   ├─ 账号池（状态机：healthy / cooldown / disabled）
   ├─ 透明转发（非流式 JSON / 流式 SSE 透传）
   ├─ 失败切换（quota → 冷却并换号；连续失败 → 自动禁用）
   ├─ SQLite 持久化（重启不丢状态与统计）
        ↓ 按账号密钥分发
   OpenCode Go 账号 A / B / C ...
        ↑
  Web 监控台（React + ECharts :48701）
```

## 快速开始

### 1. 后端（Python 3.12）

```bash
cd apps/backend
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -e ".[dev]"

# 配置账号（密钥走环境变量，不入库）
copy config\accounts.example.yaml config\accounts.yaml
set OPENCODE_GO_KEY_1=sk-xxxx   # 对应 accounts.yaml 中的 ${OPENCODE_GO_KEY_1}

.venv\Scripts\python -m uvicorn opencode_pool.app:app --host 127.0.0.1 --port 48700
```

### 2. 前端（Node 24 + pnpm 11）

```bash
cd apps/web
pnpm install
pnpm dev          # http://localhost:48701
```

### 3. 验证

```bash
curl http://127.0.0.1:48700/health
curl http://127.0.0.1:48700/api/accounts
```

浏览器打开 http://localhost:48701 查看账号状态大盘、用量趋势与统一事件时间线。

详细操作手册见 [docs/usage.md](docs/usage.md)。

## API 汇总

| 端点 | 方法 | 说明 |
|---|---|---|
| `/api/stats?hours=24` | GET | 用量聚合（按小时桶 + 按账号汇总） |
| `/api/quota?refresh=0\|1` | GET | OpenCode Go 每账号滚动/周/月额度 + 全池汇总（服务端 TTL 缓存） |
| `/api/events?limit=100&type=request,key_switch` | GET | 统一事件日志（type/data/meta/time；type 逗号分隔筛选） |
| `/api/v1/responses` | POST | OpenAI Responses 透明转发（支持流式 SSE） |
| `/api/v1/chat/completions` | POST | OpenAI Chat Completions 透明转发（支持流式 SSE） |
| `/api/v1/models` | GET | 账号池合并模型清单 |
| `/v1/*` | - | 上述三个转发端点的标准 OpenAI SDK 路径别名 |

转发示例：

```bash
curl http://127.0.0.1:48700/api/v1/responses \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-5.6-luna","input":"hi","stream":false}'
```

## 配置（.env / 环境变量）

| 变量 | 默认值 | 说明 |
|---|---|---|
| `APP_NAME` | opencode-go-pool | 应用名 |
| `LOG_LEVEL` | INFO | 日志级别 |
| `HOST` | 127.0.0.1 | 监听地址 |
| `PORT` | 48700 | 监听端口 |
| `UPSTREAM_BASE_URL` | https://api.opencode.ai/v1 | 上游默认地址（账号可覆盖） |
| `DB_PATH` | data/opencode_pool.db | SQLite 持久化路径 |
| `QUOTA_CACHE_TTL_SECONDS` | 60 | 额度查询缓存秒数（缓存期内不重复访问上游） |
| `QUOTA_TIMEOUT_SECONDS` | 10 | 单账号额度查询超时（秒） |
账号配置见 `apps/backend/config/accounts.example.yaml`（api_key 用 `${ENV_VAR}` 引用环境变量）。

## 目录结构

```
opencode-go-pool/
├─ apps/
├─ apps/
│  ├─ backend/     FastAPI 代理核心（accounts / proxy / usage / quota / store / scheduler）
│  └─ web/         React + Vite + ECharts 监控台（账号状态 / 额度 / 用量 / 事件）

## 开发规范（Rondo 方法）

- 行为规范：`AGENTS.md`
- 任务清单：`docs/TODO.yaml`（唯一执行依据）
- 推进办法：`docs/PROCESS.md`（六步闭环）
- 阶段 PRD：`docs/prd/`
- CI：push/PR 自动跑 backend（pytest/ruff）+ web（eslint/vitest/build）

## 合规边界

只支持官方 API Key 的合法接入与故障切换；不实现 Cookie 抓取、Session 复用、凭证伪造、对外转售额度等行为。多账号订阅是否允许集中到内部网关，请以 OpenCode 官方答复为准。
