# PRD-G5-代码优化·去除冗余代码（第二轮）

> 状态生命周期：草稿 → 评审 → approved（定稿）→ 开发中 → 已验收

## 元信息

| 字段 | 值 |
|---|---|
| 阶段 | G5 |
| 名称 | 代码优化 · 去除冗余代码（第二轮：图表样板收敛 + 死接口清理） |
| 状态 | approved |
| 创建日期 | 2026-08-21 |
| 定稿日期 | 2026-08-21 |
| 验收日期 | — |
| 关联文档 | docs/TODO.yaml 阶段 G5；apps/web/src/features/charts/；apps/web/src/features/dashboard/useAccountPolling.ts |

## 1. 背景与目标

- **背景**：G4 已清理显性死代码，但前端图表在 E3-E5 演进后累积了**结构性冗余**：
  1. 7 个 ECharts 组件（UsageCharts / ModelUsageChart / AccountLoadChart / ProtocolChart / ErrorTypeChart / SuccessRateTrendChart / AccountTokenShareChart）各自内联同一段生命周期样板——`echarts.init(el)` + `chart.setOption` + `window.addEventListener("resize", onResize)` + cleanup 里 `removeEventListener` + `chart.dispose()`（约 14 行 × 7 ≈ 100 行重复）。
  2. 该样板藏在 `useEffect` 里，deps 含 stats/theme/t；而大盘轮询每 10s 更新 stats，导致**每次轮询都销毁重建图表实例**（echarts.init/dispose 反复执行，WebGL canvas 上下文重建浪费）。
  3. `useAccountPolling.ts` 里定义了 `AccountsState` 接口（L18-27），但 hook 内部全部用独立 `useState`，该接口**从未被类型标注引用**——确凿死类型（全库 0 外部引用、文件内 0 次使用）。
- **目标**：把 7 份图表生命周期样板收敛为单一 `useEChart` hook（顺带修复轮询重建浪费），删除 `AccountsState` 死接口；以全量测试 + playwright 实测证明零视觉回归。
- **非目标**：不改任何图表视觉、系列、数据与交互（option 内容原样搬迁）；不改 ECharts 按需注册（`echarts.use`）与 manualChunks；不改后端与 chartData 纯函数；不统一 7 份 option 构建的差异化逻辑（tooltip formatter、deps 选择等保持组件内原样）。

## 2. 扫描/摸底方法

用临时脚本对前端做四类静态冗余分析（本轮已执行，作为清单依据）：
1. **无引用导出**：提取 `export type/interface/function/const`，统计全 src 引用次数，仅定义处出现者为候选——命中 `AccountsState`（useAccountPolling.ts，extern=0 且文件内 0 次类型标注使用）；`types/pool.ts` 中 extern=0 的类型（UsageTotals 等）均为 StatsResponse/LogsOverview 聚合类型内部引用，属活代码保留。
2. **样板重复**：对比 7 个图表组件的 `useEffect` 生命周期——init/resize/dispose/resize 监听完全一致（仅 option 与 deps 不同），确认可抽 hook。
3. **孤儿模块 / 孤儿 i18n key / 孤儿 CSS 类**：均无新增命中（CSS 类 0 命中全为 `badge-${x}`、`event-type--${x}`、`quota-...--${x}`、`summary-status__item--${x}` 模板拼接类，活代码）。
4. **未使用依赖 / 硬编码颜色 / 未用 CSS 变量**：前端依赖全部在用，TS 侧无 hex 硬编码，CSS 变量 11 定义 11 使用。

## 3. 需求范围（清理清单与依据）

### 3.1 功能需求

- [ ] FR1：新增 `src/features/charts/useEChart.ts` hook。签名 `useEChart(makeOption, deps): RefObject<HTMLDivElement>`：
  - 首挂载对 `ref.current` `echarts.init`（用 `echarts.getInstanceByDom` 判断复用，避免 StrictMode 双挂载重复 init）；
  - deps 变化时仅 `chart.setOption(makeOption(), { notMerge: true })` 更新，**不复建实例**（修复 10s 轮询重建）；
  - 统一 `window.addEventListener("resize", ... resize())`，effect cleanup 移除监听；
  - 独立卸载 effect 里 `dispose()`（真卸载时才销毁）。
- [ ] FR2：7 个图表组件全部迁移到 `useEChart`，删除各自内联样板；option 构建逻辑（含 tooltip formatter、deps 选择、`useMemo` 数据聚合）保持组件内原样。
- [ ] FR3：删除 `useAccountPolling.ts` 的 `AccountsState` 死接口（L18-27），连带无 import 需清理（该接口仅文件内定义）。
- [ ] FR4：新增 `useEChart.test.ts`（`vi.mock("echarts/core")`，jsdom）：首挂载 init 一次；deps 变化复用实例仅 setOption；addEventListener/removeEventListener 成对（unmount 后无监听残留）；卸载 dispose 被调用。

### 3.2 非功能需求

- 性能：轮询更新不再重建图表实例（消除每 10s canvas 上下文销毁重建）。
- 兼容：7 图渲染结果与迁移前视觉一致（option 内容不变）；StrictMode 开发模式无重复 init 告警。
- 维护：图表生命周期逻辑集中单点，后续新增图表不再重复样板。

## 4. 接口定义

- `useEChart`（前端内部 hook，非 HTTP 接口）：

```ts
function useEChart<T extends EChartsCoreOption>(
  makeOption: () => T,
  deps: readonly unknown[],
): React.RefObject<HTMLDivElement>;
```

- 无后端 API 变更；无导出签名变更（AccountsState 无消费者）。

## 5. 验收标准

- [ ] AC1：`useEChart.ts` 存在；7 个图表组件 grep 不再出现 `echarts.init(`、`chart.dispose()`、`addEventListener("resize"` 样板（仅 useEChart.ts 一处）。
- [ ] AC2：`AccountsState` 从 useAccountPolling.ts 删除，`grep -r AccountsState` 全库 0 命中。
- [ ] AC3：前端 `vitest` 全绿（含新增 useEChart.test）；`eslint` 0 告警；`pnpm build` 通过（strict TS 无类型错误）。
- [ ] AC4：playwright 实测监控台 7 张图均正常渲染（canvas 非空、无 console 报错）、切换主题后图表重着色、调整视口触发 resize 无异常；切统计周期（24h/3d/7d）图表数据刷新。
- [ ] AC5：后端 `pytest` + `ruff` 全绿（本阶段零后端改动，回归确认）；三联动（PRD 已验收 + TODO G5 done + CHANGELOG 追加）且 CI 全绿。

## 6. 测试计划

- 迁移前：确认 7 组件样板一致（已读源码核对）；确认图表组件未被现有 vitest 渲染（仅测 chartData 纯函数），迁移不破坏既有测试。
- 迁移后：`vitest run`（新增 useEChart 单测：init 一次 / setOption 更新 / 监听成对 / 卸载 dispose）；`eslint`；`pnpm build`。
- 浏览器：playwright `--noproxy`，加载监控台 → 等待轮询 → 逐个图表 `canvas` 存在且非空；切 dark/light 主题看四图重着色；调整窗口宽度看 resize；切 7d 周期确认数据刷新。
- 复核：重跑无引用导出扫描，AccountsState 消失且无新孤儿。

## 7. 里程碑与估算

| 子任务 | 预估 |
|---|---|
| useEChart hook + 单测 | 15 分钟 |
| 7 图表迁移（option 原地搬迁） | 25 分钟 |
| 删 AccountsState + 全量验证（vitest/eslint/build） | 15 分钟 |
| playwright 实测 + 复核扫描 | 20 分钟 |
| 三联动 + CHANGELOG | 10 分钟 |

## 8. 风险与对策

| 风险 | 对策 |
|---|---|
| 抽 hook 改变图表渲染行为（如 setOption 合并语义） | option 原样搬迁；用 `notMerge: true` 保证全量替换；AC4 playwright 逐图实测 |
| StrictMode 双挂载重复 init 告警 | `getInstanceByDom(el)` 复用已有实例；单测覆盖 init 一次 |
| dispose 时机错误导致内存/监听泄漏 | 独立卸载 effect dispose + resize 监听成对移除；单测断言 |
| option 类型不符合 EChartsCoreOption | hook 泛型 `T extends EChartsCoreOption`，组件内构建对象即可收敛 |
| 回归 10s 轮询性能 | 迁移后轮询仅 setOption 无重建（对比迁移前后 console 无 init/dispose 反复） |

## 9. 变更记录

| 日期 | 变更内容 | 理由 |
|---|---|---|
| 2026-08-21 | 初始定稿 | — |
| 2026-08-21 | 实现完成：新增 `useEChart` hook（getInstanceByDom 复用实例 + chartRef 持引用 + setOption(notMerge) + 统一 resize/dispose）；7 图表组件迁移完成（AccountLoad / AccountTokenShare / ErrorType / ModelUsage / Protocol / SuccessRateTrend / Usage），净删 109 行重复样板；删除 useAccountPolling.ts 的 AccountsState 死接口；新增 useEChart.test.tsx 5 例（init 一次 / deps 复用 / resize / 卸载 dispose / 已有实例复用） | 阶段 G5 开发 |
