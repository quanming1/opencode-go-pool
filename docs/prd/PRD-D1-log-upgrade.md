# PRD-D1-日志系统升级

## 元信息

| 字段 | 值 |
|---|---|
| 阶段 | D1 |
| 名称 | 日志系统升级（模型 / token 双协议 / 账号模型统计 / 活跃 Key / 剩余推测 / 前端分页+图表） |
| 状态 | 已验收 |
| 创建日期 | 2026-08-20 |
| 定稿日期 | 2026-08-20 |
| 验收日期 | 2026-08-20 |
| 关联文档 | docs/TODO.yaml 阶段 D1；docs/PROCESS.md |

## 1. 背景与目标

- **背景**：C4 已建立统一事件日志（type/data/meta/time 契约，可筛选 request / key_cooldown / key_switch / all_keys_* 等类型），但日志可观测性仍不足：无法回答「某个请求用的是哪个模型、消耗了多少 token」「某个 Key 收到多少次请求、分别是哪些模型」「当前哪个 Key 正在接受外部请求」「按当前消耗速率还能用多久」；前端时间线只有最近 N 条、无分页，图表只有时间桶维度，缺模型/账号维度的可视化。
- **目标**：把日志从「事件流」升级为「可观测统计 + 可翻页明细 + 维度图表」，让单用户也能直观管理账号池。
- **非目标**：
  - 不做精确账单计费（额度命中上游百分比是估算口径，非美元账单）。
  - 不做历史额度 percent 的逐点采集与时间序列预测模型（只用快照 + 本地消耗速率做线性推算）。
  - 不新增数据库表（复用 usage_events/events，仅扩展聚合与查询参数）。
  - 不动转发主路径语义（所有新能力只读 + 可选，失败降级不阻塞）。

## 2. 需求范围

### 2.1 功能需求

- [ ] FR1：请求日志记录模型与 token（双协议）。每次入站请求必须在 `usage_events` 与 `request` 事件中记录 `model` 与 token。
  - 协议 A Chat Completions：`usage.prompt_tokens` / `usage.completion_tokens`；
  - 协议 B Responses：`usage.input_tokens` / `usage.output_tokens`；
  - 提取逻辑必须分别给出可验证路径（两个字段名族的 `_extract_usage` 已存在，需补显式双协议用例）。
- [ ] FR2：按账号 × 模型聚合统计。`/api/stats` 新增 `per_account_models`：每个 Key 收到多少次请求、分别是什么模型、各自 token 与错误数。
- [ ] FR3：当前活跃 Key。新增 `GET /api/logs/overview`：返回最近成功请求使用的账号（current_active），即「当前正在接受外部请求的 Key」。
- [ ] FR4：剩余使用时长推测。`/api/logs/overview` 结合本地消耗速率与滚动额度百分比，推算「按当前速率预计还需 X 小时耗尽 / 剩余请求次数」。
- [ ] FR5：事件分页。`GET /api/events` 新增 `offset` 参数（配合 `limit` 翻页），保证不重不漏。
- [ ] FR6：前端时间线升级。EventTimeline 展示更丰富字段（模型 / 协议 / token / 耗时 / 状态码 / 账号 / 错误），并支持上一页/下一页分页。
- [ ] FR7：前端图表升级。图表区新增「模型请求分布」与「账号负载」两个维度（ECharts），数据来自 `/api/stats.per_account_models` 与 `/api/logs/overview`。

### 2.2 非功能需求

- 性能：聚合在 SQL 层完成（GROUP BY account_id, model），不对全表做 Python 侧聚合；`/api/events` 分页用 `LIMIT ? OFFSET ?`。
- 安全：所有新端点只返回脱敏账号信息（沿用 `mask_api_key`）；不暴露 `api_key` 明文、不暴露网关 key。
- 兼容性：`/api/stats` 与 `/api/events` 响应结构向后兼容（只新增字段/参数，不破坏现有字段名）；`offset` 缺省 0。
- 稳健性：无数据（空表 / quota 未取到 / 速率 0）时返回 `null` 或空数组，不抛错。
- 约束：开发与验证全程**不 kill 正在运行的 48700 后端**（用户在正常使用网关）；新功能验证用独立端口临时实例或纯测试。

## 3. 技术方案

### 3.1 分层与文件

- **store 层**（`apps/backend/src/opencode_pool/store/sqlite_store.py`）：
  - `aggregate_usage()` 扩展：追加一个 `per_account_models` 结果块（`GROUP BY account_id, model`，含 request_count / prompt_tokens / completion_tokens / error_count），空库返回 `[]`。
  - `query_events(limit, types, offset=0)`：加 `OFFSET ?`（参数化），`offset >= 0` 钳制。
  - 新增 `recent_usage_rate(minutes=60)`：返回最近 N 分钟（默认 60）每个账号成功(非 error)请求数与 token 汇总，供 FR3/FR4 使用。
- **recorder 层**（`apps/backend/src/opencode_pool/usage/recorder.py`）：`stats()` 透传 store 结果（新增 per_account_models 自动带上）。
- **API 层**：
  - `apps/backend/src/opencode_pool/api/usage.py`：`/api/stats` 返回体含新 `per_account_models` 字段。
  - `apps/backend/src/opencode_pool/api/events.py`：`/api/events` 加 `offset: int = 0`。
  - 新增 `apps/backend/src/opencode_pool/api/logs.py`：`GET /api/logs/overview`。
- **日志概览服务**（新增 `apps/backend/src/opencode_pool/logs/overview.py`）：
  - 输入：`AccountStore`（recent_usage_rate + query_events）、`QuotaSummary`（rolling avg percent 与 allocated/estimated）。
  - 输出结构：
    ```json
    {
      "current_active": {"account_id": "...", "last_success_at": "..."} | null,
      "rate": {"minutes": 60, "requests_per_minute": 1.2, "tokens_per_hour": 5000},
      "usage_remaining": {
        "estimated_requests_left": 800,
        "estimated_hours_left": 6.5,
        "basis": "rolling_percent_and_local_rate",
        "note": "估算口径：滚动窗口单账号约 2000 次，按当前速率线性推算"
      } | null
    }
    ```
- **前端**（`apps/web/src/`）：
  - `services/api.ts`：`fetchEvents(limit, offset, type)` 带 offset；新增 `fetchLogsOverview()`。
  - `types/pool.ts`：新增 `PerAccountModelUsage`、`LogsOverview`、分页类型。
  - `features/charts/EventTimeline.tsx`：字段行 + 分页（上一页/下一页 + 页码）。
  - `features/charts/UsageCharts.tsx`：新增「模型请求分布」柱状图（凭 request_count）与「账号负载」柱状图（凭 per_account request/error）。
  - `features/usage/UsagePanel.tsx`：接入 overview（当前活跃 Key + 剩余时长推测区块）与新图表数据。

### 3.2 剩余时长口径（FR4）

- 滚动窗口上限：单账号约 `2000` 次请求 / 5 小时（OpenCode Go 既定窗口，与现有 usage_limit 同源常量）。
- 可用账号数：`running accounts`（healthy 且 enabled）。
- 池剩余请求次数估算 = `(1 - rolling_avg_percent/100) × 2000 × 可用账号数`（rolling_avg_percent 为各账号滚动窗口已用百分比均值）。
- 当前速率 = 最近 60 分钟成功请求数 / 60（次/分钟）。
- 剩余小时 = 池剩余请求次数 / (速率 × 60)。
- 速率 ≤ 0 或 percent 缺失 → 输出 `null`。
- 明确标注「估算口径」，非账单保证。

## 4. 接口定义

### 4.1 GET /api/stats?hours=24（扩展）

新增字段（原有字段不变）：

```json
{
  "per_account_models": [
    {"account_id": "opencode-go-1", "model": "gpt-5.6-luna",
     "request_count": 12, "prompt_tokens": 3400, "completion_tokens": 200, "error_count": 1}
  ]
}
```

### 4.2 GET /api/events?limit=100&offset=0&type=request,key_switch

- `offset`：翻页偏移，默认 0，`0 <= offset` 钳制；响应同时返回 `offset` 与 `has_more`（是否还有更早记录）。

```json
{"events": [...], "offset": 100, "has_more": true}
```

### 4.3 GET /api/logs/overview

```json
{
  "current_active": {"account_id": "opencode-go-3", "last_success_at": "2026-08-20T12:34:56Z"} | null,
  "rate": {"minutes": 60, "requests_per_minute": 1.5, "tokens_per_hour": 6000},
  "usage_remaining": {
    "estimated_requests_left": 1200,
    "estimated_hours_left": 13.3,
    "basis": "rolling_percent_and_local_rate",
    "note": "估算口径：滚动窗口单账号约 2000 次，按当前速率线性推算"
  } | null
}
```

## 5. 验收标准

- [ ] AC1：`apps/backend/tests` 中新增双协议 token 提取用例：Chat Completions（prompt_tokens/completion_tokens）与 Responses（input_tokens/output_tokens）各自从正确字段提取并落库（`pytest -q` 通过）。
- [ ] AC2：`/api/stats` 返回含 `per_account_models`，构造多账号多模型数据后聚合正确（相同 account+model 合并计数）。
- [ ] AC3：`/api/events` 带 `offset` 翻页：`limit=2&offset=0` 与 `offset=2` 不重不漏，末页 `has_more=false`。
- [ ] AC4：`/api/logs/overview`：有最近成功请求时 `current_active` 为该账号；速率 0 或 percent 缺失时 `usage_remaining=null`。
- [ ] AC5：前端时间线分页可翻页、字段行完整（模型/token/耗时/状态码/账号）；模型分布与账号负载图表渲染 ECharts（vitest + 目检）。
- [ ] AC6：`pytest` 全量 + `ruff` 无警告；`pnpm lint` + `vitest` + build 通过。
- [ ] AC7：全程未 kill 运行中的 48700 后端；新能力验证用独立端口临时实例或测试完成。

## 6. 测试计划

- 单测：双协议 `_extract_usage` 各两条字段族用例；`aggregate_usage.per_account_models` 分组/空库/降级；`query_events` offset 翻页与钳制；`recent_usage_rate` 速率计算；`/api/logs/overview` 活跃账号/剩余推算/降级 null；`/api/events` offset 参数化。
- 前端：EventTimeline 分页切换、字段渲染；LogsOverview 区块渲染；新图表在 jsdom 下 mock ECharts 后不崩。
- 手动：独立端口临时实例启动 → 造几条请求 → 验证 stats/events/overview 返回 → 关闭实例（不碰 48700）。

## 7. 里程碑与估算

| 子任务 | 预估 |
|---|---|
| 后端：双协议 token 用例 + per_account_models + offset + overview | 主工作量 |
| 前端：时间线分页 + 字段 + 图表 + overview 区块 | 相当 |
| 测试与文档 | 中等 |

## 8. 风险与对策

| 风险 | 对策 |
|---|---|
| 双协议 token 字段遗漏（用户点名重点） | 显式双协议用例锁定两个字段族；`_extract_usage` 平铺兼容 input/prompt 双命名 |
| 剩余推测口径被误解为账单 | 输出携带 `note` 明确"估算口径"；前端标注"估算" |
| 新端点拖慢 `/api/stats` | 聚合走 SQL GROUP BY，走索引 id 排序；滥用量可控（单用户） |
| 误杀运行中的 48700 | 开发全程不启停该进程；验证用独立端口临时实例 |

## 9. 变更记录

| 日期 | 变更内容 | 理由 |
|---|---|---|
| 2026-08-20 | 初始定稿 | 用户发起日志系统升级功能（模型/token 双协议/按 Key 模型统计/剩余推测/活跃 Key/前端分页+图表），覆盖 TODO D1 立项范围 |
| 2026-08-20 | 后端实现完成：新增 `/api/logs/overview`、`/api/stats` 扩展 `per_account_models`、`/api/events` 支持 `offset` 分页；双协议 token 提取补显式测试；store 新增 `recent_usage_rate` | D1 后端开发收口，行为变更留痕（测试 135 passed + 独立端口端到端实测通过） |
| 2026-08-20 | 前端实现完成：事件时间线自包含分页（20 条/页 + offset 翻页 + 自动刷新首帧）与字段详情展开；新增运行概览卡（活跃 Key/速率/剩余时长）与模型分布、账号负载两张 ECharts 图 | D1 前端开发收口（vitest 33 + eslint 0 + build 通过），分页数据源改为 `/api/events?offset` |
