# PRD-E1-响应式开发

## 元信息

| 字段 | 值 |
|---|---|
| 阶段 | E1 |
| 名称 | 响应式开发（多分辨率/窗口尺寸下不挤压、不溢出） |
| 状态 | approved |
| 创建日期 | 2026-08-20 |
| 定稿日期 | 2026-08-20 |
| 验收日期 | （验收后填写） |
| 关联文档 | docs/TODO.yaml 阶段 E1；docs/PROCESS.md |

## 1. 背景与目标

- **背景**：监控台目前是桌面向布局（左侧 180px 固定 tab 栏 + 右侧内容区）。实测各视口存在明显挤压/溢出：
  - 360px 视口：sidebar 固定 180px 占半屏，`.page-main` 仅剩 180px，扣除 padding 后内容区只有约 132px；`account-list`（minmax 260px）、`summary-status__items`、`quota-row`、`overview-grid`、`keys-table` 等网格/表格的最小内容宽度超过容器，元素右缘溢出到屏幕外（实测 right 达 405-515px）。
  - 480px 视口：sidebar 占 37.5% 宽度浪费；额度均值三列每列仅 70px，临界挤压。
  - 768px：无横向溢出，但中间网格在临界值附近。
  - 1024/1440px：良好。
- **目标**：建立断点体系，让监控台在从手机（360px）到宽屏（1440px+）的任意窗口下：布局不横向溢出、文字/UI 不被挤压、核心操作完整可达。
- **非目标**：
  - 不改变桌面（≥1280px）的现有视觉与布局。
  - 不做移动端专属交互（抽屉/汉堡菜单保留即可，不做手势）。
  - 不动后端 API 与数据语义，纯前端 CSS/结构层改造。

## 2. 需求范围

### 2.1 功能需求

- [ ] FR1：断点体系。建立 1280 / 1024 / 768 / 576（含 360 最低保障）四档断点，所有响应式规则统一挂在这些断点上。
- [ ] FR2：窄屏（≤576px）侧栏折叠为顶部 tab。`Sidebar` 从「左侧固定 180px 竖排」变为「顶部等宽横排 tab 条」，内容区占满全宽。
- [ ] FR3：内容区网格自适应。`account-list` / `summary-cards` / `overview-grid` / `summary-status__items` 在窄屏改为单列（或不再以固定最小宽度撑破容器），任意视口无横向溢出。
- [ ] FR4：表格防挤压。`keys-table` 在窄屏允许容器内横向滚动（保留完整列），表头/单元格不换行挤压。
- [ ] FR5：文字/间距自适应。`page-header` / `page-main` / `.card` 在小屏收紧内边距；`event-timeline` 时间与摘要在小屏可换行展示完整信息；按钮组 `flex-wrap`。
- [ ] FR6：图表/概览不被挤压。ECharts 容器（chart-box）保持 100% 宽自适应，卡片内文字不重叠。

### 2.2 非功能需求

- 兼容性：纯 CSS media query，不动 JS 状态；桌面端（≥1280）视觉零回归。
- 性能：无新增运行时逻辑，无新增 JS 依赖。
- 可维护性：断点集中注释说明；不引入内联 style 覆盖。
- 测试：vitest/eslint/build 保持全绿；playwright 多视口断言无横向溢出与关键元素不越界。

## 3. 技术方案

### 3.1 断点定义（按 width）

| 断点名称 | 值 | 说明 |
|---|---|---|
| `--bp-lg` | 1280px | 宽屏（默认桌面布局，无限流改动） |
| `--bp-md` | 1024px | 中等屏：中间网格额外列数收敛（现有 @900 卡可改为 1024 下的 1 列） |
| `--bp-sm` | 768px | 平板：summary 卡片网格单列（现有 @900 已做）、quota-head 保持 2 列 |
| `--bp-xs` | 576px | 手机：侧栏折叠为顶部 tab、padding 收紧、全部网格单列、表格横滚 |

说明：现有代码已有 @900/@720 两处 media query，本次统一收敛为 1024/768/576 三档（900 并入 1024，720 并入 768/576），避免断点碎片化。

### 3.2 文件与改动

- **`apps/web/src/layout.css`**（骨架，核心改动）：
  - `.page-header`：默认 16px 24px；@576 → 12px 16px，`flex-wrap: wrap`。
  - `.page-body`：默认 `row`；@576 → `flex-direction: column`。
  - `.sidebar`：默认 180px 竖排；@576 → `width: auto`、`flex-direction: row`、去掉右边框改底边框、`flex-wrap: wrap`。
  - `.sidebar-tab`：@576 → `flex: 1`、文字居中、去掉底边框、增加右边框分隔。
  - `.page-main`：默认 padding 24px；@768 → 16px；@576 → 12px。
  - `.keys-create`：`flex-wrap: wrap`（已具备则保持）。
  - 新增 `.keys-table-wrap`：`overflow-x: auto`；`keys-table` 设 `min-width` 保证列不挤压（如 640px），表结构完整靠容器滚动。
- **`apps/web/src/features/dashboard/dashboard.css`**：
  - `.account-list`：`auto-fill minmax(260px,1fr)` → @768 `minmax(0,1fr)`；@576 单列 `grid-template-columns: 1fr`。
  - `.summary-cards`：grid 两列（`minmax(220,0.75fr) minmax(440,2fr)`）→ @1024 单列（替换/收敛现有 @900 规则为 @1024）；@576 不变单列。
  - `.summary-card__quota-head`：三个分栏（title+averages+status）→ @1024 变两行（title+averages 同行、status 换行）→ @576 变纵向排列（flex column，现有 @720 规则收敛到 @576）。
  - `.summary-card__quota-averages`：`repeat(3, minmax(70px,1fr))` → @576 `grid-template-columns: 1fr 1fr 1fr` 且宽度 100% 或改 flex wrap。
  - `.summary-status__items`：三列固定 → @576 保持 3 列但在释放侧栏后每列有充足宽度（≥100px）。
  - `.overview-grid`：`auto-fit minmax(220px,1fr)` → @576 单列（`grid-template-columns: 1fr`）。
  - `.quota-row`（账号卡内 36px/1fr/auto）：@576 保持，释放侧栏后宽度充足；`.quota-row__reset` 已占整行无需改。
  - `.event-timeline__pager` / `.event-timeline__item`：@576 时间列缩小（min-width 150→100px），摘要 `white-space: normal` 允许换行（保留完整信息）。
  - `.card`：@576 padding 16→12px。
- **`apps/web/src/components/Sidebar.tsx` / `App.tsx`**：如需为顶部 tab 增加可访问性/结构微调（如 tab 用 flex 布局已由 CSS 承担，一般不改 JS；如无必要不动）。

### 3.3 关键防溢出原则（对所有网格/弹性容器）

- 用 `minmax(0, 1fr)` 取代可能撑破的固定 `minmax(260px, ...)` 于容器更窄时。
- 长文本默认可断行/省略：`overflow-wrap: break-word`、`min-width: 0`（flex/grid 子项）。
- 表格类不压缩列，改用父容器横向滚动。

## 4. 接口定义

无接口变更（纯前端样式/结构，后端 API 不动）。前端结构新增 `.keys-table-wrap` 载体。

## 5. 验收标准

- [ ] AC1：playwright 在 1440/1024/768/480/360 五个视口下，`document.documentElement.scrollWidth === clientWidth`（无横向溢出）。
- [ ] AC2：playwright 断言关键区块（`.summary-card__quota-title`/`.summary-status__items`/`.account-card`/`.quota-row`/`.overview-cell`/`.keys-table`）在 360 视口下 `getBoundingClientRect().right <= vw`。
- [ ] AC3：≤576 视口下 sidebar 呈顶部横排（`.sidebar` 宽为视口宽而非 180px），内容区占满全宽。
- [ ] AC4：`keys-table` 在 360 视口下完整列可通过容器横向滚动查看（容器 overflow-x 生效，表右侧不溢出视口外）。
- [ ] AC5：桌面 1440/1024 视口视觉与改造前一致（无回归）。
- [ ] AC6：`pnpm lint` + `vitest` + `build` 全绿。
- [ ] AC7：全程未杀运行中的 48700/48701（仅在现有 dev server 上热更验证）。

## 6. 测试计划

- 单元/静态：现有 vitest 保持通过（样式改动不影响逻辑组件测试；如 Sidebar 结构改动则补断言）。
- 手动（playwright MCP 实测）：五档视口逐一执行 AC1-AC4 的 DOM/布局断言，记录结果。
- 回归：桌面视口截图对比改造前后（无阴影无圆角纯白风格不因响应式改动）。

## 7. 里程碑与估算

| 子任务 | 预估 |
|---|---|
| layout.css 骨架断点 + sidebar 折叠 | 主工作量 |
| dashboard.css 网格/表格/文字防挤压 | 主工作量 |
| playwright 五视口验证 + 收尾 | 中等 |

## 8. 风险与对策

| 风险 | 对策 |
|---|---|
| 桌面端视觉回归 | 断点只加不删默认规则；1440/1024 验收对照截图 |
| 断点碎片化（旧 900/720） | 统一收敛为 1024/768/576，删旧片段 |
| 表格横滚被误判"没适配" | 容器滚动 + 完整列是移动端表格标准做法，PRD 内明确口径 |
| ECharts 在容器变窄后不重绘 | chart-box 100% 宽 + resize 监听（已有 UsageCharts/ModelUsageChart 监听 window resize） |

## 9. 变更记录

| 日期 | 变更内容 | 理由 |
|---|---|---|
| 2026-08-20 | 初始定稿 | 用户发起响应式开发需求（不同窗口/分辨率不挤压、适配），覆盖 TODO E1 立项范围 |
