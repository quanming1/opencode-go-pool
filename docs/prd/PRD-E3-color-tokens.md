# PRD-E3-主题切换·颜色token化

> 状态生命周期：草稿 → 评审 → approved（定稿）→ 开发中 → 已验收

## 元信息

| 字段 | 值 |
|---|---|
| 阶段 | E3 |
| 名称 | 主题切换 · 颜色 token 化 |
| 状态 | 已验收 |
| 创建日期 | 2026-08-21 |
| 定稿日期 | 2026-08-21 |
| 验收日期 | 2026-08-21 |
| 关联文档 | docs/TODO.yaml 阶段 E3；apps/web/src/theme/tokens.ts；apps/web/src/i18n/index.tsx；apps/web/src/index.css |

## 1. 背景与目标

- **背景**：E2 已实现 light/dark 主题切换（CSS 变量 `:root` + `html[data-theme="dark"]` 两套 9 色 token，CSS 全站已用 `var(--color-*)` 消费）。但 **JS 侧存在第二套独立颜色源**：`src/i18n/index.tsx` 的 `chartColors(theme)` 用 10 处硬编码 hex 维护 ECharts 图表配色（canvas 无法直接读 CSS 变量）。同一批颜色在 CSS 与 TS 各写一份，改配色/加主题时必须同步改两处，容易漂移。
- **目标**：建立 `src/theme/tokens.ts` 作为 JS 侧颜色 token 的唯一入口（light/dark 各 9 色 + 图表派生色板），`chartColors` 收敛进 tokens 删除硬编码；新增单测解析 `index.css` 的 `--color-*` 定义并断言与 `tokens.ts` 完全一致——把"两处写值"钉死为"一处改、测试即报警"的语义单源；主题切换（CSS 变量原生联动 + ECharts 动态取色）行为不变。
- **非目标**：不做运行时用 JS 注入 CSS 变量（会引入 jsdom 测试环境差异与无 JS 降级风险）；不新增第三主题/跟随系统（超出本阶段范围，后续可扩）；不改任何业务颜色值（纯结构调整，色值原样搬移）。

## 2. 需求范围

### 2.1 功能需求

- [ ] FR1：新建 `src/theme/tokens.ts`：
  - `type Theme = "light" | "dark"`（与现有类型合并，避免重复定义）；
  - `interface ColorTokens`（9 色：`bg` / `bg-subtle` / `text` / `text-secondary` / `border` / `accent` / `ok` / `warn` / `danger`，类型字符串收窄）；
  - `lightTokens` / `darkTokens` 常量（值必须与 `index.css` 的 `:root` 与 `html[data-theme="dark"]` 逐条一致）；
  - `colorTokens(theme): ColorTokens` 选择器与 `chartColors(theme)`（返回 `{accent, ok, danger, border, label}` 图表派生色板，`label` 取 `text-secondary`）——**JS 侧不再出现任何硬编码 hex**。
- [ ] FR2：`src/i18n/index.tsx` 删除 `chartColors` 的 10 处硬编码 hex 实现，改为从 `../theme/tokens` re-export（保持 `Theme` 类型与 `chartColors` 符号对外兼容，`App.tsx` 等既有 import 不破）。
- [ ] FR3：三个 ECharts 组件（`UsageCharts` / `ModelUsageChart` / `AccountLoadChart`）的 `chartColors` import 从 `../../i18n` 改为 `../../theme/tokens`（关注点分离：theme 域独立于 i18n 域）；渲染逻辑与主题联动不变。
- [ ] FR4：新增 `src/theme/tokens.test.ts`：解析 `src/index.css` 文本中 `:root` 块与 `html[data-theme="dark"]` 块内的 `--color-*: <hex>` 定义，断言与 `lightTokens` / `darkTokens` 完全一致（共 18 对，防止双源漂移）；`chartColors(theme)` 派生键值用例。
- [ ] FR5：`index.css` 的颜色变量定义处加注释标注"单源见 src/theme/tokens.ts"；README / README.zh-CN 主题与 token 说明同步（一行级说明即可）。

### 2.2 非功能需求

- 零数据变更：18 个颜色值原样搬移，主题切换视觉效果零回归。
- 保持 import 兼容（`I18nProvider`/`useTheme` 仍在 `i18n/index.tsx`，App 侧无感）。
- 无新增依赖（纯 TS 常量 + 现有 vitest）。
- token 消费统一：今后新增 JS 侧用色一律从 `theme/tokens.ts` 取。

## 3. 技术方案

### 3.1 目录与文件

```
apps/web/src/
├─ theme/
│  ├─ tokens.ts        # 新建：Theme + ColorTokens + light/dark + colorTokens + chartColors（唯一 JS 色源）
│  └─ tokens.test.ts   # 新建：与 index.css 一致性断言 + chartColors 派生用例
├─ i18n/
│  └─ index.tsx        # 删除 chartColors 硬编码；re-export { chartColors, type Theme } from "../theme/tokens"
└─ features/charts/
   ├─ UsageCharts.tsx      # import { chartColors } from "../../theme/tokens"
   ├─ ModelUsageChart.tsx  # 同上
   └─ AccountLoadChart.tsx # 同上
```

### 3.2 tokens.ts 关键结构（示意）

```ts
export type Theme = "light" | "dark";
export interface ColorTokens {
  bg: string; "bg-subtle": string; text: string; "text-secondary": string;
  border: string; accent: string; ok: string; warn: string; danger: string;
}
export const lightTokens: ColorTokens = { /* 与 index.css :root 一致 */ };
export const darkTokens: ColorTokens = { /* 与 index.css html[data-theme="dark"] 一致 */ };
export function colorTokens(theme: Theme): ColorTokens { return theme === "dark" ? darkTokens : lightTokens; }
export interface ChartPalette { accent: string; ok: string; danger: string; border: string; label: string; }
export function chartColors(theme: Theme): ChartPalette {
  const c = colorTokens(theme);
  return { accent: c.accent, ok: c.ok, danger: c.danger, border: c.border, label: c["text-secondary"] };
}
```

> 说明：CSS 变量值为 CSS 侧必须内联（浏览器原生主题切换；canvas 需 JS 取值），故 CSS 与 TS 各写一份；**一致性由 tokens.test.ts 强制**——任何一处改动若不同步，CI 即红，等价于语义单源。

### 3.3 一致性单测（tokens.test.ts 思路）

- 读 `src/index.css` 源码文本；
- 用正则切出 `:root { ... }` 与 `html[data-theme="dark"] { ... }` 两段；
- 各自解析 `--color-(key): (#hex)` 到 `{ key: value }`；
- 断言 `=== lightTokens` / `=== darkTokens`（逐 key，缺失/多余/值不同均失败）；
- `chartColors("light"|"dark")` 派生结果键值断言（label 映射 text-secondary 等）。

## 4. 接口定义

- `chartColors(theme)` 签名与语义保持（5 键色板），仅实现来源迁移；外部调用方（三个 ECharts 组件）无感知。
- `Theme` 类型从 `theme/tokens` 一处定义，`i18n/index.tsx` re-export 保持 `App.tsx` 兼容。

## 5. 验收标准

- [ ] AC1：`src/theme/tokens.ts` 存在且导出 `Theme` / `ColorTokens` / `lightTokens` / `darkTokens` / `colorTokens` / `chartColors`；`lightTokens`/`darkTokens` 各 9 色与 `index.css` 逐条一致（由单测断言通过）。
- [ ] AC2：全局 grep `src/` 的 ts/tsx 中无业务硬编码 hex（`chartColors` 10 处已删除；排除 CSS 变量定义与测试 fixture）。
- [ ] AC3：`vitest` 全绿（含新增 `tokens.test.ts`；`chartColors` 派生值与原实现一致）；`eslint` 0 告警；`pnpm build` 通过。
- [ ] AC4：playwright 回归：切 dark 后 `html[data-theme]="dark"`、body 背景/文字为深色 token、三张 ECharts 图系列色随 dark 变化；切回 light 恢复——主题联动无回归。
- [ ] AC5：README（英文）与 README.zh-CN 含颜色 token 单源说明；CHANGELOG `[未发布]` 追加 E3。

## 6. 测试计划

- 一致性：`tokens.test.ts` 断 CSS 与 TS 18 对颜色等价（含故意改一处应失败的负例验证）。
- 回归：`vitest run` 全量 + `eslint` + `pnpm build`。
- 浏览器：playwright 两主题切换断言（背景/文字/图表系列色）。

## 7. 里程碑与估算

| 子任务 | 预估 |
|---|---|
| tokens.ts 编写 | 20 分钟 |
| i18n 收敛 + 三图表 import 迁移 | 15 分钟 |
| tokens.test.ts 编写 | 25 分钟 |
| 本地 vitest/eslint/build + 负例验证 | 15 分钟 |
| playwright 两主题回归 | 15 分钟 |
| README/CHANGELOG 同步 | 10 分钟 |

## 8. 风险与对策

| 风险 | 对策 |
|---|---|
| 色值搬移抄错导致观感漂移 | 单测 18 对硬断言；负例先行验证测试灵敏 |
| `Theme` 类型两处定义漂移 | 只在 `theme/tokens.ts` 定义，`i18n/index.tsx` re-export |
| chartColors 迁移后 ECharts 不刷新 | 组件已以 `theme` 为 useEffect 依赖重绘（E2 已实现），行为不变 |
| 循环依赖（theme ↔ i18n） | tokens.ts 不 import i18n（纯 TS 常量）；仅 i18n 单向往 theme 取 |

## 9. 变更记录

| 日期 | 变更内容 | 理由 |
|---|---|---|
| 2026-08-21 | 初始定稿 | — |
| 2026-08-21 | 实现完成：新增 src/theme/tokens.ts（Theme/ColorTokens/light/dark/colorTokens/chartColors 9 色×2）；chartColors 硬编码移出 i18n/index.tsx 改为 re-export；三个 ECharts 组件 import 走 theme/tokens；新增 tokens.test.ts 断言 CSS 变量与 tokens 18 对一致（含负例验证）；devDependencies 声明 @types/node；README 同步 | 阶段 E3 开发 |
| 2026-08-21 | 验收通过：vitest 44 passed（含 tokens.test 6）+ eslint 0 + build 通过；负例验证（改 CSS 色值测试即红）；playwright 实测 dark 背景 #111827/文字 #f9fafb、light 背景 #ffffff/文字 #1f2937、三张 ECharts 图 canvas 在切换后正常；src 无业务硬编码 hex（仅 token 定义两处） | 阶段 E3 完成 |
