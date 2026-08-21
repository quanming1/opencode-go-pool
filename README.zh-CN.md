# OpenCode Go Pool

多个 OpenCode Go 订阅账号合并为一个逻辑上游的代理服务 + 可视化监控台。

[English](README.md)

## 解决什么问题

单个 OpenCode Go 账号有 5 小时调用窗口限制，不够用时把多个订阅账号组成一个池子：某账号额度耗尽（429/限流）自动冷却并切换到下一个账号，对客户端呈现为一个统一 API 入口。配套 Web 大盘实时查看账号状态、用量趋势、额度情况与统一事件日志。

## 功能

- **账号池状态机**：healthy / cooldown / disabled；额度/鉴权失败自动冷却，连续失败自动禁用，惰性 + 定时恢复。
- **透明转发**：同时透传 OpenAI Responses 与 Chat Completions 两种协议，支持非流式 JSON 与流式 SSE。
- **失败轮换**：额度/网络/服务错误时熔断当前账号并重试下一个健康账号；每个请求返回 `X-Pool-Account` 头。
- **SQLite 持久化**：账号状态与用量统计重启不丢（WAL 模式）。
- **网关鉴权**：可选 Bearer 校验转发与管理端点（默认关闭，面向本地单用户）。
- **额度展示**：官方 OpenCode Go `/usage` 接口按账号实时滚动/周/月额度，服务端 TTL 缓存 + 单账号降级。
- **监控大盘**：账号状态卡、用量与轮换趋势图（ECharts）、额度总览、统一事件时间线（请求/冷却/切换/失效/网关 key 生命周期）。
- **一键启动**：`python start.py` 清理 48700/48701 端口旧进程（含 uvicorn --reload 孤儿进程）并静默启动前后端，带健康检查。
- **CI/CD 自动打包**：每次 push/PR 自动构建后端 wheel 与前端 dist，组装成完整发布包并验证（全新 venv 安装 + 资源完整性），产物上传为可下载 artifact；打 `v*` tag 时自动发布到对应 GitHub Release。
- **多语言 + 主题（颜色 token 化）**：内置中/英切换与亮/暗主题；全站颜色统一为 CSS 变量，并由 `src/theme/tokens.ts` 提供 JS 侧镜像（ECharts 等 JS 消费端的单一取色来源；CSS 变量与 TS token 一致性由单测强制）。

## 架构

```
客户端（ftre / 任意 OpenAI Responses 调用方）
        ↓  OpenAI 协议（Responses / Chat Completions）
  OpenCode Go Pool 代理（FastAPI :48700）
   ├─ 账号池（状态机：healthy / cooldown / disabled）
   ├─ 透明转发（JSON / 流式 SSE 透传）
   ├─ 失败切换（quota → 冷却并换号；连续失败 → 自动禁用）
   ├─ SQLite 持久化（重启不丢状态与统计）
        ↓ 按账号密钥分发
   OpenCode Go 账号 A / B / C ...
        ↑
  Web 监控台（React + ECharts :48701）
```

## 快速开始

### 一键启动（推荐）

首次完成下方手动安装步骤（后端 .venv + 前端 pnpm install）后，日常开发只需：

```bash
python start.py
```

自动清理 48700/48701 端口旧进程（含 uvicorn --reload 的孤儿子进程）→ 静默启动前后端 → 健康检查。
日志写 `logs/backend.log` 与 `logs/web.log`（已 gitignore）；再次运行即重启。

### 1. 后端（Python 3.12）

```bash
cd apps/backend
python -m venv .venv
.venv\Scripts\activate          # Windows（Linux/macOS: source .venv/bin/activate）
pip install -e ".[dev]"

# 配置账号（密钥走环境变量，不入库）
copy config\accounts.example.yaml config\accounts.yaml   # Windows
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

浏览器打开 http://localhost:48701 查看账号状态大盘、用量趋势、额度与统一事件时间线。

详细操作手册见 [docs/usage.md](docs/usage.md)。

## API 汇总

| 端点 | 方法 | 说明 |
|---|---|---|
| `/health` | GET | 健康检查（status + version） |
| `/api/accounts` | GET | 账号池总览（key 脱敏） |
| `/api/stats?hours=24` | GET | 用量聚合（按小时桶 + 按账号汇总） |
| `/api/quota?refresh=0\|1` | GET | 各账号滚动/周/月额度 + 全池汇总（服务端 TTL 缓存） |
| `/api/events?limit=100&type=request,key_switch` | GET | 统一事件日志（type/data/meta/time；type 逗号分隔筛选） |
| `/api/keys` | GET/POST | 网关 API Key 列表 / 创建（明文仅展示一次） |
| `/api/accounts/{id}/clear\|disable\|enable` | POST | 账号控制（需鉴权） |
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
| `UPSTREAM_TIMEOUT` | 60 | 上游请求超时（秒） |
| `POOL_SCAN_INTERVAL_SECONDS` | 60 | 冷却扫描间隔（秒） |
| `MAX_CONSECUTIVE_FAILURES` | 3 | 连续失败自动禁用阈值 |
| `DB_PATH` | data/opencode_pool.db | SQLite 持久化路径 |
| `QUOTA_CACHE_TTL_SECONDS` | 60 | 额度查询缓存秒数（缓存期内不重复访问上游） |
| `QUOTA_TIMEOUT_SECONDS` | 10 | 单账号额度查询超时（秒） |

账号配置见 `apps/backend/config/accounts.example.yaml`（`api_key` 用 `${ENV_VAR}`（如 `${OPENCODE_GO_KEY_1}`）引用环境变量）。密钥只存本地 `.env` / 环境变量，绝不入库。

可选网关鉴权：在 `.env.keys`（已 gitignore）中设 `GATEWAY_AUTH=on` 开启 Bearer 校验、`GATEWAY_MASTER_KEY` 注册主 key。网关 key 在库中以 SHA-256 哈希存储，明文仅创建时展示一次。

## 目录结构

```
opencode-go-pool/
├─ apps/
│  ├─ backend/     FastAPI 代理核心（accounts / proxy / usage / quota / store / scheduler）
│  └─ web/         React + Vite + ECharts 监控台（账号状态 / 额度 / 用量 / 事件）
├─ docs/           TODO.yaml / PROCESS.md / prd/ / usage.md / security-audit.md
└─ start.py        一键启动脚本（Windows）
```

## 开发规范（Rondo 方法）

- 行为规范：`AGENTS.md`
- 任务清单：`docs/TODO.yaml`（唯一执行依据）
- 推进办法：`docs/PROCESS.md`（六步闭环）
- 阶段 PRD：`docs/prd/`
- CI/CD：push/PR 自动跑 backend（pytest + ruff + 构建 wheel）/ web（eslint + vitest + build），随后 pack job 组装并验证完整发布包、上传 artifact（见 [CI/CD 打包验证](#cicd-打包验证)）
- 分支：Git Flow + 全 PR 流（main/develop 不直接提交；feature 分支经 PR 合入，commit scope 强制关联阶段 id）

## CI/CD 打包验证

每次 push/PR 运行三个 job（`.github/workflows/ci.yml`）：

1. **backend**：lint / test / `python -m build` 产出 `opencode_pool` wheel（上传 artifact `backend-dist`）；
2. **web**：lint / test / 构建 `dist/`（上传 artifact `web-dist`）；
3. **pack**：下载两产物后运行 `scripts/package_release.py`（纯标准库，本地也可跑）组装 `opencode-go-pool-<version>.zip`（后端 wheel + 前端 dist + start.py + 文档 + 示例配置）。脚本会校验包：wheel 能在全新临时 venv 安装并 import 出版本一致、`dist/index.html` 引用的资源全部在包内存在。最终 zip 上传为 artifact `release-package`。

推送 `v*` tag 时，发布包还会自动上传到同 tag 的 GitHub Release（不存在则自动创建），每个版本都带一个开箱即用的归档。

## 合规边界

只支持官方 API Key 的合法接入与故障切换；不实现 Cookie 抓取、Session 复用、凭证伪造、对外转售额度等行为。多账号订阅是否允许集中到内部网关，请以 OpenCode 官方答复为准。

## License

[MIT](LICENSE)
