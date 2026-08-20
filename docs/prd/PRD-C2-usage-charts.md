# PRD-C2-用量统计与轮换趋势图

> 状态生命周期：草稿 → 评审 → approved（定稿）→ 开发中 → 已验收

## 元信息

| 字段 | 值 |
|---|---|
| 阶段 | C2 |
| 名称 | 用量统计与轮换趋势（后端统计 + 前端 ECharts） |
| 状态 | approved |
| 创建日期 | 2026-08-20 |
| 定稿日期 | 2026-08-20 |
| 验收日期 | — |
| 关联文档 | docs/TODO.yaml 阶段 C2；docs/prd/PRD-B2（转发）PRD-B4（持久化）；前端 App.tsx / Dashboard |

## 1. 背景与目标

- **背景**：C1 已能看账号当前状态（/api/accounts），但看不到**历史用量**（请求量 / Token）与**轮换事件**（谁在何时被冷却/切换）——这正是判断"多账号合并是否值得、哪家账号最稳"的核心观测数据。后端目前没有用量统计，切换历史只在 SQLite 落库未暴露 HTTP。
- **目标**：后端新增用量统计记录与聚合 API、切换历史 HTTP API；前端用 ECharts 展示请求量/Token 用量趋势折线 + 轮换事件时间线，与 C1 大盘同页展示。
- **非目标**：不做精确的按模型/按账号的 billing 计费（本轮按账号聚合即可）；不做历史清洗/归档（数据量小，保留 N 条即可）；不做实时 websocket 推送（沿用 C1 轮询）。

## 2. 需求范围

### 2.1 功能需求

- [ ] FR1 后端-用量记录：`UsageRecorder` 在每次 `/api/v1/responses` 转发完成后（成功或失败）记录一条用量：`ts` / `account_id` / `kind(success|error)` / `error_type`（出错时）/ `prompt_tokens` / `completion_tokens` / `request_count`（恒 1）/ `model`（若有）。从响应体提取 token usage（Responses 协议 `usage.prompt_tokens` / `usage.completion_tokens`，缺失则 0）。
- [ ] FR2 后端-用量持久化：与 B4 同库（SQLite），新增表 `usage_events`；`UsageRecorder.save()` 增量写；保留最近 N=2000 条并裁剪。
- [ ] FR3 后端-聚合 API `GET /api/stats?hours=24`：按小时桶聚合返回：`buckets: [{ts, request_count, prompt_tokens, completion_tokens, error_count}]`；另含 `totals`（总请求/总 token/总错误）、`per_account`（各账号请求数与 token，便于看哪家最稳）。
- [ ] FR4 后端-切换历史 API `GET /api/switch-history?limit=50`：返回账号池切换历史（新→旧），字段 `ts/account_id/kind/reason`；kind 用中文语义映射（quota→额度限制、auth→鉴权、server→上游错误、recover→恢复、disable→禁用、enable→启用、clear→清除）。
- [ ] FR5 前端-用量趋势图：ECharts 折线图展示请求量（柱）+ Token 用量（折线）双轴，按小时；标题"用量趋势（近24h）"。
- [ ] FR6 前端-轮换事件时间线：列表展示最近切换事件（时间 / 账号 / 事件类型 / 原因），格式化中文，空态"暂无轮换事件"。
- [ ] FR7 前端-集成：Dashboard 下方增加两个区块（图表 + 时间线），复用 C1 轮询（10s）；加载/错误态沿用现有模式。

### 2.2 非功能需求

- 性能：统计查询走 SQLite 聚合（hours 桶数有限）；前端图表数据量小。
- 健壮性：用量记录失败不影响转发主路径（try/except + 降级）；DB 不可用时统计返回空。
- 可测：UsageRecorder / stats 聚合 / switch-history 都是纯逻辑可单测；前端图表组件用固定数据可断言。

## 3. 技术方案

### 后端

```
apps/backend/src/opencode_pool/
├─ usage/
│  ├─ __init__.py       # 导出 UsageRecorder
│  └─ recorder.py       # UsageRecorder：save() / aggregate(hours) / switch_history(limit)
├─ api/usage.py         # APIRouter：/api/stats、/api/switch-history
└─ store/sqlite_store.py# 扩展：建 usage_events 表 + save_usage + aggregate_usage + load_switch_history
```

- `UsageRecorder` 使用与 `AccountStore` 同一 SQLite 连接（B4 已建），构造传入 store。
- `save(event)` → `store.save_usage(...)`；表结构：

```sql
CREATE TABLE IF NOT EXISTS usage_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    account_id TEXT NOT NULL,
    kind TEXT NOT NULL,            -- success | error
    error_type TEXT,
    prompt_tokens INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    request_count INTEGER NOT NULL DEFAULT 1,
    model TEXT
);
```

- 聚合 SQL（按小时桶）：

```sql
SELECT strftime('%Y-%m-%dT%H:00:00', ts) AS bucket,
       SUM(request_count), SUM(prompt_tokens), SUM(completion_tokens),
       SUM(CASE WHEN kind='error' THEN 1 ELSE 0 END)
FROM usage_events
WHERE ts >= strftime('%Y-%m-%dT%H:%M:%S', 'now', ?)
GROUP BY bucket ORDER BY bucket;
```

- per_account 聚合：`SELECT account_id, SUM(request_count), SUM(prompt_tokens), SUM(completion_tokens), SUM(error_count) ... GROUP BY account_id`。
- Forwarder 接线：转发后（success 分支与 error 分支）调用 `usage_recorder.save(...)`；从响应体解析 token——非流式 JSON `usage`；流式在 aiter 结束时最后一块或不可能精确（本轮：流式成功记 token=0，仅计请求数；非流式精确）。

### 前端

- `services/api.ts` 追加 `fetchStats(hours)`、`fetchSwitchHistory(limit)`。
- `types/pool.ts` 追加 `StatsResponse / SwitchEvent`。
- 新文件：
```
apps/web/src/features/charts/
├─ UsageCharts.tsx     # ECharts 折线/柱（接收 stats 数据）
└─ SwitchTimeline.tsx  # 轮换事件时间线列表
```
- `Dashboard.tsx` 在统计摘要下渲染 `<UsageCharts stats={...} />` 与 `<SwitchTimeline events={...} />`，数据并入轮询：fetchAccounts + fetchStats + fetchSwitchHistory（Promise.all 或独立 hook）。
- ECharts：A3 已引入 echarts/core + LineChart；追加 BarChart 与 `echarts/components` 的 Grid/Tooltip 已具备；`usage` 模块化引入即可。

## 4. 接口定义

- `GET /api/stats?hours=24`：

```json
{
  "hours": 24,
  "totals": { "request_count": 120, "prompt_tokens": 9000, "completion_tokens": 3000, "error_count": 3 },
  "per_account": [
    { "account_id": "opencode-go-1", "request_count": 100, "prompt_tokens": 8000, "completion_tokens": 2500 }
  ],
  "buckets": [
    { "ts": "2026-08-20T08:00:00", "request_count": 40, "prompt_tokens": 3000, "completion_tokens": 1000, "error_count": 1 }
  ]
}
```

- `GET /api/switch-history?limit=50`：

```json
{ "events": [
  { "ts": "2026-08-20T09:00:00", "account_id": "opencode-go-1", "kind": "quota", "reason": "rate limit", "kind_label": "额度限制" }
] }
```

## 5. 验收标准

- [ ] AC1：pytest 全绿（新增 test_usage.py / test_usage_api.py）。
- [ ] AC2：ruff 无警告。
- [ ] AC3：`UsageRecorder.save()` 后 `store.aggregate_usage(hours)` 返回正确桶/汇总/per_account（用注入 ts 验证）。
- [ ] AC4：`GET /api/stats` 返回 200 且结构字段齐全；空库返回全 0。
- [ ] AC5：`GET /api/switch-history` 返回切换事件 + kind_label 中文映射；空态返回空数组。
- [ ] AC6：前端 `pnpm lint && pnpm test && pnpm build` 全过（新增 UsageCharts / SwitchTimeline 测试）。
- [ ] AC7：UI 目检：Dashboard 显示用量统计卡 + 折线图 + 事件时间线；白底直角无阴影。
- [ ] AC8：转发一条请求后（fake 上游），`/api/stats` 请求数 +1，显示对应账号（端到端 TestClient）。

## 6. 测试计划

- 后端：recorder save 幂等；aggregate buckets 按小时聚合正确；per_account 正确；空库语义；switch-history kind_label 映射。
- 集成：TestClient 造 usage + 打 /api/stats 与 /api/switch-history；Forwarder 注入 fake 上游后验证记录成功/失败（复用 MockTransport）。
- 前端：UsageCharts 传入固定 stats 渲染（mock echarts 或断言容器存在）；SwitchTimeline 渲染事件/空态/中文 label；Dashboard 集成。

## 7. 里程碑与估算

| 子任务 | 预估 |
|---|---|
| usage/recorder.py + store 扩展 | 25 分钟 |
| api/usage.py + Forwarder 接线 | 30 分钟 |
| 后端测试 | 30 分钟 |
| 前端 types + api + ECharts 图表 + 时间线 | 40 分钟 |
| 前端测试 + 目检 | 25 分钟 |

## 8. 风险与对策

| 风险 | 对策 |
|---|---|
| 流式 token 无法精确 | 流式成功记 token=0 仅计数；非流式精确；PRD 明确边界 |
| SQLite 时间聚合跨时区 | 用 ISO 存 UTC；聚合按 UTC 小时桶，前端展示本地化 |
| echarts 二次引入类型/大小 | 模块化引入（bar/line/grid/tooltip/canvas），复用现有 echarts 实例模式 |
| 统计拖慢转发 | save 在转发返回后异步/降级；DB 不可用 catch 掉 |

## 9. 变更记录

| 日期 | 变更内容 | 理由 |
|---|---|---|
| 2026-08-20 | 初始定稿 | — |
