# PRD-E4-图表优化·更丰富数据展示

> 状态生命周期：草稿 → 评审 → approved（定稿）→ 开发中 → 已验收

## 元信息

| 字段 | 值 |
|---|---|
| 阶段 | E4 |
| 名称 | 图表优化 · 更丰富数据展示 |
| 状态 | 开发中 |
| 创建日期 | 2026-08-21 |
| 定稿日期 | 2026-08-21 |
| 关联文档 | docs/TODO.yaml 阶段 E4；apps/backend/src/opencode_pool/store/sqlite_store.py；apps/backend/src/opencode_pool/api/usage.py；apps/web/src/features/charts/；apps/web/src/types/pool.ts |

## 1. 背景与目标

- **背景**：监控台现有三图（`UsageCharts` 请求量+token、`ModelUsageChart` 模型请求数、`AccountLoadChart` 账号请求+错误）数据维度单一，而系统早已采集并保留了大量**未展示**的真实数据：request 事件含 `duration_ms`（耗时）/ `protocol`（responses / chat/completions）/ `status_code` / `attempts`；usage_events 含 `kind='success'/'error'` 与 `error_type`。用户明确要求"图表优化，展示更丰富的数据"。
- **目标**：后端 `/api/stats` 在不改表结构的前提下扩展出**成功率、耗时分位、协议分布、错误类型分布**四类新维度；前端三图富化 + 新增「运行汇总」卡（总请求/成功率/总 token/平均耗时/活跃模型）+ 协议分布与错误类型分布两个小图，让已采集的数据前可视化。
- **非目标**：不改 usage_events/events 表结构（不做新列）；不做长期耗时时序（耗时/协议来自 events 近期窗口，注明口径）；不改账号池/转发逻辑；不新增 JavaScript 依赖（图表仍用 ECharts 现有构建 + 按需注册）。

## 2. 需求范围

### 2.1 功能需求（后端）

- [ ] FR1：`aggregate_usage` 增强（基于 usage_events，不动表结构）：
  - `totals` 增加 `success_count`（`SUM(CASE WHEN kind='success' THEN request_count ELSE 0 END)`）与 `success_rate`（success/(success+error)，分母为 0 时 1.0）；
  - `per_account`、`per_account_models`、`buckets` 各增加 `success_count`（前端可据此算各自的成功率）；
  - 顶层新增 `error_types`：`kind='error'` 按 `error_type` 分组计数（`[{type, count}]`，count 降序），提供错误分布。
- [ ] FR2：新增 `store.events_summary(limit=500)`（基于 events 表近 N 条 request 事件）：
  - `duration_ms: {avg, p95, max}`（request 事件的耗时汇总，`null` 当无可统计数据）；
  - `protocol: [{name, count}]`（request 事件 `protocol` 分布，降序，如 responses / chat_completions）；
  - `event_counts: {key_switch, key_cooldown_started, key_disabled, all_keys_unavailable, all_keys_invalid}`（近期切换/冷却/禁用/全失效计数，EventType 名作为键）；
  - `window` 字段标注统计条数（如 500）。
- [ ] FR3：`GET /api/stats` 合并返回：原结构（hours/totals/per_account/per_account_models/buckets）+ 新增 `error_types` + `summary`（含 FR2 结果）。空库/不可用降级为全 0 / 空数组 / `null`（不报错）。

### 2.2 功能需求（前端）

- [ ] FR4：`types/pool.ts` 扩展 `StatsResponse`：`success_count/success_rate`（totals 内）、`error_types`、`summary`（duration/protocol/event_counts/window）；各新增字段用**可选**类型 + 渲染端默认值容错（运行中旧后端未 reload 前不会报错）。
- [ ] FR5：三图富化：
  - `UsageCharts`：请求量 bar + token line 保留；**新增错误 bar 系列（error_count，danger 色）** + tooltip 显示成功/错误/成功率；
  - `ModelUsageChart`：除请求数外，**tooltip 显示该模型成功/错误率与 prompt/completion token**；图例说明更明确；
  - `AccountLoadChart`：除请求+错误外，**新增成功率 line（右轴，ok 色）**，tooltip 显示 token。
  - 空数据（0 模型/0 账号）时显示空态文案而非空白图。
- [ ] FR6：新增「运行汇总」`StatsSummaryCard`（放图区顶部一行）：总请求数、成功率、总 token（prompt+completion）、平均耗时（ms）、活跃模型数、活跃账号数；数据来自 `stats.totals` + `stats.summary`。
- [ ] FR7：新增两个小图：
  - 协议分布 `ProtocolChart`（ECharts Pie，注册 PieChart）：responses / chat_completions 占比；
  - 错误类型 `ErrorTypeChart`（ECharts Bar）：`error_types` 前 N 类。
  - 无数据时渲染空态。
- [ ] FR8：新增/更新 i18n key（zh/en）与全部文案 t() 化；颜色统一走 `theme/tokens.ts`。

### 2.3 非功能需求

- 兼容：`/api/stats` 仅**新增键**，不破坏既有消费（旧 JSON 结构不变）。
- 性能：events_summary 仅近 500 条，JSON 解析量可忽略。
- 口径注释：duration/protocol/event_counts 标注"近 N 条事件"统计窗口。
- 不主动重启运行中的 48700 后端：后端改动验证走 pytest + 独立端口临时实例；前端对旧字段容错。

## 3. 技术方案

### 3.1 后端

- `sqlite_store.py`：
  - `aggregate_usage` 各 SELECT 增加 `SUM(CASE WHEN kind='success' THEN request_count ELSE 0 END) AS success_count`；`totals` 计算 `success_rate`（`success+error` 为 0 → 1.0）；
  - 新增 `error_types` 查询：`SELECT error_type, COUNT(*) ... WHERE kind='error' AND error_type IS NOT NULL GROUP BY error_type ORDER BY COUNT(*) DESC`；
  - 新增 `events_summary(limit=500)`：用现有 `query_events(limit, types=['request','key_switch','key_cooldown_started','key_disabled','all_keys_invalid','all_keys_unavailable'])` 或直接查 `events` 表（event_time DESC, limit）；解析 `data_json` 聚合 request 的 `duration_ms`/`protocol`，对 `key_switch` 等类型计数；p95 算法：排序后取 `ceil(n*0.95)-1` 索引。
- `api/usage.py`：`/api/stats` 把 `recorder.stats(hours)` 结果与 `store.events_summary()` 合并为 `{**stats, "error_types": ..., "summary": ...}`。

### 3.2 前端

- `types/pool.ts`：扩展接口（新增字段 `optional`）。
- `StatsSummaryCard.tsx`（新增）：一行 flex 指标卡（label + 值）；值格式化（耗时 ms、token 千分位）。
- `ProtocolChart.tsx`（新增）：ECharts Pie，色板 `chartColors`（accent/ok/...）；注册 `PieChart`。
- `ErrorTypeChart.tsx`（新增）：ECharts Bar（等价 `chart-box` 小容器）。
- 三图注入新系列/新 tooltip 内容。
- `UsagePanel.tsx`：图区顶部放 `StatsSummaryCard`，图表网格加入两小图。
- `i18n/messages.ts`：新增 `summary.*`、`chart.legend.*`、`chart.protocol.*`、`chart.errorType.*` 等 key（zh/en 双字典一致，由现有 i18n 单测断言）。
- `theme/tokens.ts`：不新增色值（复用 accent/ok/danger/warn + 派生 label/border）。

## 4. 接口定义

`GET /api/stats?hours=24` 返回（新增段加粗说明）：

```jsonc
{
  "hours": 24,
  "totals": {
    "request_count": 123,
    "prompt_tokens": 1000,
    "completion_tokens": 900,
    "error_count": 3,
    "success_count": 120,        // FR1 新增
    "success_rate": 0.9756       // FR1 新增
  },
  "per_account": [ { "account_id": "a1", "request_count": .., "prompt_tokens": ..,
                     "completion_tokens": .., "error_count": .., "success_count": .. } ],
  "per_account_models": [ { "account_id": .., "model": .., "request_count": ..,
                            "prompt_tokens": .., "completion_tokens": ..,
                            "error_count": .., "success_count": .. } ],
  "buckets": [ { "ts": "..", "request_count": .., "prompt_tokens": ..,
                 "completion_tokens": .., "error_count": .., "success_count": .. } ],
  "error_types": [ { "type": "quota", "count": 2 }, { "type": "bad_request", "count": 1 } ],  // FR1 新增
  "summary": {                                                           // FR3 新增
    "window": 500,
    "duration_ms": { "avg": 812, "p95": 2450, "max": 4800 },             // 可 null
    "protocol": [ { "name": "chat_completions", "count": 80 }, { "name": "responses", "count": 40 } ],
    "event_counts": { "key_switch": 5, "key_cooldown_started": 3, "key_disabled": 1,
                      "all_keys_unavailable": 0, "all_keys_invalid": 0 }
  }
}
```

## 5. 验收标准

- [ ] AC1：后端 pytest：insert 成功/失败样本后 `aggregate_usage` 的 `success_count/success_rate/error_types` 正确；`events_summary` 的 duration 分位、protocol 分布、event_counts 正确；空库返回降级值不抛。（新增 test_sqlite_store / test_usage 用例）
- [ ] AC2：`/api/stats` 合并返回含 `error_types` 与 `summary`，且旧字段结构不变（旧 pytest 用例全绿）。
- [ ] AC3：bulk: ruff 0 告警；pytest 全绿。
- [ ] AC4：前端三图富化 + 汇总卡 + 两小图渲染新数据；`StatsResponse` 新字段容错（可选类型）；vitest（汇总卡/协议/错误/格式化用例）全绿；eslint 0；`pnpm build` 通过。
- [ ] AC5：独立端口临时实例（不碰 48700）实测 `/api/stats` 新字段返回正确；playwright 打开监控台图表可见、空态/有数据均正常。
- [ ] AC6：三联动（PRD 已验收 + TODO E4 done + CHANGELOG）且 CI 三 job 绿。

## 6. 测试计划

- 后端：`test_sqlite_store.py` 加 success_count/success_rate/error_types/events_summary 用例；`test_usage_api.py` 加 /api/stats 组合返回断言。
- 前端：`StatsSummaryCard`、`ProtocolChart`、`ErrorTypeChart` 渲染用例（mock stats/summary）；三图 seed 值用例；i18n 新 key 一致性由现有 i18n.test 覆盖。
- E2E：独立端口实例 + playwright。

## 7. 里程碑与估算

| 子任务 | 预估 |
|---|---|
| 后端 aggregate_usage 增强 + events_summary + /api/stats 合并 | 40 分钟 |
| 后端 pytest 新增用例 | 25 分钟 |
| 前端 types + 三图富化 | 40 分钟 |
| 前端 StatsSummaryCard + ProtocolChart + ErrorTypeChart + i18n | 40 分钟 |
| vitest 用例 + eslint/build | 20 分钟 |
| 独立实例 + playwright 验证 | 20 分钟 |
| 三联动 + CHANGELOG | 10 分钟 |

## 8. 风险与对策

| 风险 | 对策 |
|---|---|
| events 5000 条保留窗口 → 耗时/协议为"近期"统计 | summary.window 标注口径；PRD 非目标已声明 |
| 旧后端未 reload 前前端拿不到新字段 | 新字段全部 optional + 渲染默认值容错 |
| p95 空/单点计算 | duration 样本 < 2 时 avg/max 可用、p95=null 或回落 max；用例锁定 |
| 新增 PieChart 增加包体 | 已 manualChunks 拆 echarts；按需注册增量极小 |
| 401/403 等 AUTH 错误无 duration？request 事件均有 duration_ms（含失败） | events_summary 只统计有 duration_ms 的 request 事件；无则忽略 |

## 9. 变更记录

| 日期 | 变更内容 | 理由 |
|---|---|---|
| 2026-08-21 | 初始定稿 | — |
| 2026-08-21 | 实现完成：后端 aggregate_usage 补 success_count/success_rate（totals/per_account/per_model/buckets）+ error_types 分布；新增 store.events_summary（耗时分位 avg/p95/max、协议分布、key_switch 等事件计数，近 500 条，p95 需 ≥2 样本）；/api/stats 经 recorder.stats 合并 summary。前端 StatsResponse 扩容（可选字段容错旧后端）；三图增强（错误系列/成功率线/tooltip 富化）；新增 StatsSummaryCard（运行汇总）+ ProtocolChart（Pie）+ ErrorTypeChart（Bar）+ i18n/样式；StatsSummaryCard 单测 3 项 | 阶段 E4 开发 |
