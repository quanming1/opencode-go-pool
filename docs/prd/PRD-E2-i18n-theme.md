# PRD-E2-中英文切换与主题切换

## 元信息

| 字段 | 值 |
|---|---|
| 阶段 | E2 |
| 名称 | 中英文切换 + 主题切换（light/dark） |
| 状态 | approved |
| 创建日期 | 2026-08-20 |
| 定稿日期 | 2026-08-20 |
| 验收日期 | （验收后填写） |
| 关联文档 | docs/TODO.yaml 阶段 E2；docs/PROCESS.md |

## 1. 背景与目标

- **背景**：监控台目前 UI 文案全部硬编码中文（扫描 13 个组件约 265 处中文片段），无法切换语言；配色是固定白底（`index.css :root` 8 个颜色变量），无法切换明暗主题；ECharts 系列色在图表组件内硬编码字面量。
- **目标**：
  1. 中英文一键切换（header 控件），localStorage 持久化；
  2. 浅色/深色主题一键切换（header 控件），localStorage 持久化，全站（含 ECharts）随动；
  3. 保持现有白色简洁 UI 规范（直角、无阴影）不变形。
- **非目标**：
  - 不做多语言文件加载/懒加载（文案量小，内置字典即可）。
  - 不做跟随系统主题（`prefers-color-scheme` 可作为默认值来源，但不自动跟随）。
  - 不引入 i18next/react-i18next 等第三方 i18n 依赖（项目依赖引入谨慎，文案量几十条，自研足够）。
  - 不改变后端任何内容。

## 2. 需求范围

### 2.1 功能需求

- [ ] FR1：语言切换。header 提供「中文 / EN」切换；切换后全站 UI 文案（导航、卡片标题、按钮、徽章、图表 legend/tooltip、时间线标签与摘要、状态文案、表单）即时切换；选择持久化到 localStorage，刷新保持。
- [ ] FR2：主题切换。header 提供「浅色 / 深色」切换；`html[data-theme="dark"]` 时全站背景/文字/边框/强调色/语义色随动；ECharts 系列色与网格线同步切深色；持久化到 localStorage，刷新保持。
- [ ] FR3：默认值。首次访问语言默认中文（保持现状）、主题默认浅色；localStorage 无值时不闪烁。

### 2.2 非功能需求

- 依赖：不新增 npm 依赖（纯自研 + CSS 变量）。
- 性能：切换即时，无网络请求；字典内置在 bundle。
- 兼容性：React 19；localStorage 不可用时（隐私模式）降级为内存态，不抛错。
- 可维护性：文案 key 按组件/区块前缀组织（如 `nav.usage`、`summary.available`、`chart.legend.requests`），zh/en 字典互为镜像 key 集（ts 类型约束保证不遗漏）。

## 3. 技术方案

### 3.1 i18n（新增 `apps/web/src/i18n/`）

- `messages.ts`：`export const messages = { zh: {...}, en: {...} } as const`，key 按前缀组织；`export type MessageKey = keyof typeof messages["zh"]`；用类型断言保证 en 与 zh 的 key 集合一致（`en satisfies Record<MessageKey, string>`）。
- `I18nContext.tsx`（或 `i18n.tsx`）：`I18nProvider`（state `locale`，`t(key[, vars])` 支持 `{var}` 插值，`setLocale`），localStorage key `ocp.locale`；`useI18n()` hook。
- 文案替换：13 个组件中所有面向用户的字符串改为 `t("...")`；保留纯代码/测试标识符。

### 3.2 主题（CSS 变量）

- `index.css :root` 现有 8 个变量即浅色主题；新增 `:root` 补充变量 `--color-bg-subtle: #f9fafb`（原硬编码的背景色）、`--color-text-inverse`；新增 `html[data-theme="dark"]` 覆盖全部变量：
  - bg `#111827`、bg-subtle `#1f2937`、text `#f9fafb`、text-secondary `#9ca3af`、border `#374151`、accent `#3b82f6`、ok `#22c55e`、warn `#f59e0b`、danger `#ef4444`。
- 硬编码颜色变量化：`layout.css` 3 处 `#f9fafb` → `var(--color-bg-subtle)`。
- 主题切换：`setTheme()` 写入 `html.dataset.theme` + localStorage `ocp.theme`；启动时读取 localStorage（无则 light）设置 `html.dataset.theme`（在 React 渲染前执行，防闪烁）。
- ECharts 动态取色：图表组件初始化时从 `getComputedStyle(document.documentElement)` 读 `--color-accent/--color-ok/--color-danger/--color-border/--color-text-secondary` 生成 option；主题变化时派发自定义事件 `ocp:themechange`（或依赖 React state）触发图表重绘。采用：主题 context 提供 `theme`，图表组件 `useEffect([theme])` 重设 option。

### 3.3 控件与布局

- header（`App.tsx`/header 组件）右侧新增：语言切换（下拉或两个相邻按钮「中文 / EN」）+ 主题切换（按钮「浅色/深色」或太阳/月亮——本项目禁 emoji，用文字按钮）。
- 控件自包含 i18n（语言按钮显示两种语言当前项，主题按钮文字随当前主题）。

### 3.4 文件与改动

- 新增：`apps/web/src/i18n/messages.ts`、`apps/web/src/i18n/index.tsx`（Provider + hook + useTheme）。
- 修改：
  - `apps/web/src/main.tsx`：包 `<I18nProvider>` + 启动读取 localStorage 设置 `html[data-theme]` 与 tab 初始语言。
  - `apps/web/src/App.tsx`：header 加入切换控件；文案替换。
  - `apps/web/src/index.css`：变量化补全 + dark 覆盖。
  - `apps/web/src/layout.css`：3 处 `#f9fafb` → `var(--color-bg-subtle)`。
  - 13 个组件：文案 → `t()`（Sidebar、UsagePanel、SummaryCards、AccountCard、StatusBadge、AccountControls、LogsOverviewCard、EventTimeline、UsageCharts、ModelUsageChart、AccountLoadChart、KeysPanel）。
  - 纯函数适配：`eventSummary.ts` 的 EVENT_LABELS / buildSummary 的中文片段——改为接收已翻译 label 或返回 key 由调用方 t()（选择：buildSummary 接收 `(t, type, data)` 或在组件内替换文案，保留结构函数与 i18n 解耦：EVENT_LABELS 改为供组件做 labelOf(type)，组件内用 t()；buildSummary 输出结构文本由组件按 t() 拼接）。

## 4. 接口定义

无后端接口变更。前端内部：`useI18n(): { locale, setLocale, t }`、`useTheme(): { theme, toggleTheme }`。

## 5. 验收标准

- [ ] AC1：playwright 点「EN」后：header 标题、Tab 名、卡片标题、状态徽章、按钮、时间线标签与摘要均为英文；刷新后保持英文。
- [ ] AC2：playwright 点「深色」后：`html[data-theme="dark"]` 生效，body/卡片背景为深色变量、文字变浅、边框变深；ECharts 画布系列色与文字颜色变深色；刷新后保持。
- [ ] AC3：zh 与 en 字典 key 集合一致（ts 类型约束 + vitest 断言 `Object.keys(messages.zh)` 与 en 相等）。
- [ ] AC4：无遗漏面向用户的中文硬编码（vitest/扫描：除注释、`data-testid`、受控的 `as const` 结构标记外，渲染文本均经 t()）。
- [ ] AC5：`pnpm lint` + `vitest` + `build` 全绿。
- [ ] AC6：localStorage 不可用时（测试注入抛错）页面不崩，切换回退内存态。
- [ ] AC7：全程未杀运行中的 48700/48701（仅在 dev server 热更验证）。

## 6. 测试计划

- 单元：i18n 字典完整性（zh/en key 一致）、t() 插值、useTheme 设置 html 属性与 localStorage、localStorage 抛错降级。
- 组件：App header 控件渲染与切换调用；已替换 t() 的组件快照文案变化。
- 手动（playwright）：AC1/AC2 逐项断言。

## 7. 里程碑与估算

| 子任务 | 预估 |
|---|---|
| i18n 基建 + 字典 + 控件 | 中等 |
| 主题变量化 + ECharts 动态色 | 中等 |
| 13 组件文案替换 + 时间线摘要适配 | 主工作量 |
| 验证 + 收尾 | 中等 |

## 8. 风险与对策

| 风险 | 对策 |
|---|---|
| 文案替换遗漏导致中英混杂 | 字典 key 类型约束 + vitest 扫描断言 + playwright 抽查 |
| ECharts 主题切换不重绘 | 图表组件以 theme 为依赖的 useEffect 重设 option，统一动态取色 |
| localStorage 禁用 | try/catch + 内存回退（AC6） |
| 主题改变破坏现有白色 UI 规范 | dark 是新增变量覆盖，light 默认零改动；直角无阴影约束不变 |

## 9. 变更记录

| 日期 | 变更内容 | 理由 |
|---|---|---|
| 2026-08-20 | 初始定稿 | 用户发起中英文切换 + 主题切换功能，覆盖 TODO E2 立项范围 |
