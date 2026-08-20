# PRD-E5-图表再深化·周期切换与构成展示

> 状态生命周期：草稿 → 评审 → approved（定稿）→ 开发中 → 已验收

## 元信息

| 字段 | 值 |
|---|---|
| 阶段 | E5 |
| 名称 | 图表再深化 · 周期切换与构成展示 |
| 状态 | 开发中 |
| 创建日期 | 2026-08-21 |
| 定稿日期 | 2026-08-21 |
| 关联文档 | docs/TODO.yaml 阶段 E5；apps/web/src/features/charts/；apps/web/src/features/dashboard/useAccountPolling.ts；apps/web/src/features/usage/UsagePanel.tsx；apps/web/src/i18n/messages.ts |

## 1. 背景与目标

- **背景**：E4 已把成功率/耗时/协议/错误类型等维度加入 `StatsResponse` 与前端图表，但运行中的 48700 后端是孤儿 worker（无 --reload 热载），新字段暂未上屏。与此同时，`/api/stats` 早已支持 `?hours=`（1..168，后端 clamp），前端却固定 24h；buckets 里一直有 `prompt_tokens/completion_tokens/request_count/error_count` 的**构成与成功率信息**也未可视化。用户持续要求"图表优化，展示更丰富的数据"。
- **目标**：本轮**零后端改动、纯前端深化**，用现有接口数据立即把图表做丰富：①时间周期切换（24h / 3d / 7d）；②Token 构成拆分（prompt/completion 堆叠）；③小时级成功率趋势折线；④账号 Token 占比环图。因运行中后端不被触碰，前端热载后即可看到真实数据。
- **非目标**：不改后端一行代码（避开孤儿 worker 热载问题，全程不 kill/重启 48700）；不作事件计数图（依赖 E4 `summary`，等后端热载后再补）；不新增依赖；不做跨 Tab。

## 2. 需求范围

### 2.1 功能需求

- [ ] FR1：时间周期切换
  - `useAccountPolling` 新增 `statsHours` 状态与 `setStatsHours(h: 24 | 72 | 168)`；`refresh` 依赖 `statsHours`，切换后立即重取 `/api/stats?hours=<h>`（继续沿用 10s 轮询）；
  - `UsagePanel` 趋势卡头新增周期按钮组（24h / 72h / 168h，`data-testid="stats-hours-24|72|168"`，选中项 disabled）；
  - 趋势图 X 轴标签自适应：窗口 ≤48h 显示 `HH:MM`，>48h 显示 `MM-DD HH:MM`（`b.ts.slice` 调整）。
- [ ] FR2：Token 构成拆分：`UsageCharts` 的 Token 折线改为 **prompt/completion 堆叠柱**（右轴，`stack: "token"`），保留请求量/错误柱（左轴）；legend 增加「输入 Token / 输出 Token」。
- [ ] FR3：小时级成功率趋势图 `SuccessRateTrendChart`（Line，y 轴 0-100%）：
  - 数据从 `buckets` 推算（兼容旧后端）：每桶 `ok = success_count ?? (request_count - error_count)`，`rate = total>0 ? ok/total : null`（无请求为断点，`connectNulls`，不显示）；
  - 放在小图栅格，`data-testid="success-rate-trend-chart"`；无任何可算数据时显示空态。
- [ ] FR4：账号 Token 占比环图 `AccountTokenShareChart`（Pie）：
  - 数据 `per_account` 的 `prompt_tokens + completion_tokens`，过滤 `tokens>0`，占比展示；
  - 色板沿用 `chartColors` 多色，`data-testid="account-token-share-chart"`；无 token 数据时空态。
- [ ] FR5：布局与文案
  - 图区改为「小图栅格」：protocol（已有）/ error types（已有）/ success rate / token share 四张小图自适应排布（`auto-fit minmax(220px,1fr)`，窄屏单列）；
  - i18n 中英新增 key：`chart.title.successRate`、`chart.title.tokenShare`、`chart.legend.prompt`、`chart.legend.completion`、`chart.period.24h/72h/168h`、`stats.hours`（周期标注）等；文案全部 t() 化，颜色走 `theme/tokens.ts`。

### 2.2 非功能需求

- **零后端改动**：所有新展示基于现有 `/api/stats` 响应字段（hours/per_account/per_account_models/buckets/prompt/completion/error/request_count）。
- 容错：旧后端（无 success_count/summary 等）通过推算/可选字段降级，不崩溃、不误导（无数据用 `null`/空态）。
- 不新增 npm 依赖；ECharts 仅按需注册（LineChart/PieChart 已在 E4 引入）。

## 3. 技术方案

### 3.1 数据层（useAccountPolling.ts）

```ts
const [statsHours, setStatsHours] = useState<24 | 72 | 168>(24);
// refresh 内 fetchStats(statsHours)；useCallback deps 加 statsHours；
return { ..., statsHours, setStatsHours };
```

### 3.2 图表

- `UsageCharts.tsx`：series 改四系列——request bar(左,accent)、error bar(左,danger)、prompt 堆叠柱(右,accent)、completion 堆叠柱(右,ok,同 `stack:"token"`)；X 轴 label 由 `stats.hours` 决定 `slice(11,16)` 或 `slice(5,16)`。
- `SuccessRateTrendChart.tsx`（新）：Line 0-100；`data = buckets.map(rate)`（`number|null`）；`connectNulls: true`。
- `AccountTokenShareChart.tsx`（新）：Pie；`data = per_account.filter(tokens>0).map({name: account_id, value: tokens})`；色板循环。
- 两新图复用 `chart-box-sm` 容器与既有 useEffect/chartColors 模式。

### 3.3 布局（UsagePanel.tsx）

- 周期按钮组放「用量趋势」card-head-row 右侧（与 quota 刷新同款）。
- 新「小图栅格」section：`.mini-chart-grid` 内四张小卡（各自标题 + 图或空态）；protocol/error types 从原独立 section 移入栅格。

## 4. 接口定义

- 无 API 变更。前端消费既有 `/api/stats?hours={24|72|168}`（后端已支持 1..168 钳制）。

## 5. 验收标准

- [ ] AC1：`useAccountPolling` 暴露 `statsHours`/`setStatsHours`，切换后重新请求 `?hours=`；对应前端单测（mock fetch 断言 URL）。
- [ ] AC2：`UsageCharts` Token 为 prompt/completion 堆叠双系列；24h 与 7d 下 X 轴标签格式不同（逻辑函数可测）。
- [ ] AC3：`SuccessRateTrendChart` 成功率纯函数计算正确（含旧字段回退 `request-error` 与空桶 `null`）；`AccountTokenShareChart` 占比纯函数正确（过滤 tokens=0、降序）；两图空态。
- [ ] AC4：小图栅格四卡自适应排布（≥1024 多列、≤576 单列——复用 E1 断点体系）；周期按钮 data-testid 齐全。
- [ ] AC5：vitest 全绿（新增成功率/占比/周期切换用例）+ eslint 0 + `pnpm build` 通过；playwright 实测：周期切换改变趋势数据、Token 堆叠/成功率趋势/账号占比图真实渲染（基于运行中 48700 旧后端即可出真数据）。
- [ ] AC6：三联动（PRD 已验收 + TODO E5 done + CHANGELOG）且 CI 三 job 绿。

## 6. 测试计划

- 前端：`SuccessRateTrendChart`/`AccountTokenShareChart` 的纯函数单测（rateMap/tokenShare）+ `useAccountPolling` hours 切换用例 + 既有用例回归。
- E2E：playwright 打开监控台，切 24h/7d、确认趋势变化与三新图渲染（旧后端下成功率推算、Token 拆分数据真实）。

## 7. 里程碑与估算

| 子任务 | 预估 |
|---|---|
| useAccountPolling hours 状态 + 单测 | 20 分钟 |
| UsageCharts Token 堆叠 + X 轴自适应 | 25 分钟 |
| SuccessRateTrendChart + AccountTokenShareChart | 35 分钟 |
| UsagePanel 周期按钮 + 小图栅格 + i18n + 样式 | 30 分钟 |
| vitest/eslint/build + playwright | 25 分钟 |
| 三联动 + CHANGELOG | 10 分钟 |

## 8. 风险与对策

| 风险 | 对策 |
|---|---|
| 7d 窗口桶很多导致图挤 | X 轴标签 48h 切换格式；`axisLabel` 自动隐藏间隔（不强制 interval:0） |
| 旧后端无 success_count | 成功率推算 `request-error`；两者皆缺才 `null` |
| 四张小图页面变长 | `auto-fit minmax` 栅格自适应，窄屏单列；沿用 E1 断点 |
| hours 切换与轮询竞态 | `setStatsHours` 更新触发 refresh（deps 含 statsHours），旧请求由 Promise.allSettled 兜底 |

## 9. 变更记录

| 日期 | 变更内容 | 理由 |
|---|---|---|
| 2026-08-21 | 初始定稿 | — |
| 2026-08-21 | 实现完成（纯前端零后端改动）：useAccountPolling 加 statsHours/setStatsHours（24/72/168，refresh 依赖周期）；UsageCharts Token 拆 prompt/completion 堆叠柱 + X 轴标签随窗口自适应（>48h MM-DD HH:MM）；新增 chartData.ts 纯函数（bucketLabel/bucketSuccessRates/accountTokenShare）+ SuccessRateTrendChart（小时成功率折线，旧字段回退 request-error、空桶断点）+ AccountTokenShareChart（账号 Token 占比环图）；UsagePanel 趋势卡周期按钮组 + 「构成分析」小图栅格（成功率/Token 占比/协议/错误类型四图自适应）；ChartPalette 补 warn 色；i18n 中英新 key | 阶段 E5 开发 |
