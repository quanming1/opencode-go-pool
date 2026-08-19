# PRD-A3-前端ReactVite骨架

> 状态生命周期：草稿 → 评审 → approved（定稿）→ 开发中 → 已验收

## 元信息

| 字段 | 值 |
|---|---|
| 阶段 | A3 |
| 名称 | 前端 React + Vite + ECharts 骨架 |
| 状态 | 已验收 |
| 创建日期 | 2026-08-19 |
| 定稿日期 | 2026-08-19 |
| 验收日期 | 2026-08-19 |
| 关联文档 | docs/TODO.yaml 阶段 A3 |

## 1. 背景与目标

- **背景**：监控台（C 阶段）需要前端展示账号状态与用量趋势。A3 先搭可运行的前端骨架：Vite 工程、React、ECharts 引入、白色简洁 UI 基础样式与一个基础页面。
- **目标**：`apps/web/` 是可构建可运行的 Vite + React + TS 工程，`pnpm build` 成功，UI 严格遵守白色简洁规范（无阴影、无圆角）。
- **非目标**：不实现账号大盘与图表业务（C 阶段）；不接后端真实 API（骨架阶段用静态占位）；不做路由（单页起步）；不做 Electron 打包。

## 2. 需求范围

### 2.1 功能需求

- [ ] FR1：`apps/web/` 为 Vite + React + TypeScript 工程（package.json、vite.config.ts、tsconfig、index.html）。
- [ ] FR2：ECharts 已安装并可用——首页包含一个 ECharts 静态示例图（折线图，数据写死），验证图表管线可用。
- [ ] FR3：UI 设计规范落地为全局样式：
  - 背景纯白 #FFFFFF；正文深灰 #1F2937；边框 #E5E7EB 细线；
  - 全站 border-radius: 0；全站禁用 box-shadow / drop-shadow；
  - 强调色单一（如 #2563EB），语义色仅用于状态（绿/黄/红）。
- [ ] FR4：基础页面（App 单页）：页头（项目名 + 版本号）、主区（占位卡片：欢迎文案 + ECharts 示例图）。
- [ ] FR5：工程脚本：`dev` / `build` / `preview` / `lint`（eslint）/ `test`（vitest）；至少一个 vitest 用例。
- [ ] FR6：样式方案用纯 CSS（全局 index.css + 局部模块），不引入 UI 组件库。

### 2.2 非功能需求

- 性能：build 产物 gzip 后 < 300KB（骨架阶段估算，echarts 全量约 1MB，用按需引入控制）。
- 兼容性：现代 Chromium（Electron 目标环境）。
- 可维护：TypeScript strict 开启。

## 3. 技术方案

- 工程：`pnpm create vite`（react-ts 模板）后裁剪。
- 依赖：react、react-dom、echarts（按需 import：`echarts/core` + LineChart + 必要组件）、eslint/prettier、vitest。
- 目录：

```
apps/web/
├─ package.json
├─ vite.config.ts
├─ tsconfig.json
├─ index.html
└─ src/
   ├─ main.tsx
   ├─ App.tsx
   ├─ index.css          # 全局：白色简洁、无阴影、无圆角
   ├─ features/
   │  └─ demo/           # 骨架阶段示例图（C 阶段替换为 dashboard/charts）
   │     └─ DemoChart.tsx
   └─ test/
      └─ App.test.tsx
```

- ECharts 按需引入：`echarts/core` + `LineChart` + `GridComponent` + `TooltipComponent` + `CanvasRenderer`，控制产物体积。

## 4. 接口定义

- UI 规范 token（全局 CSS 变量）：

```css
:root {
  --color-bg: #FFFFFF;
  --color-text: #1F2937;
  --color-border: #E5E7EB;
  --color-accent: #2563EB;
  --radius: 0;            /* 全站无圆角 */
  --shadow: none;         /* 全站无阴影 */
}
```

## 5. 验收标准

- [ ] AC1：`cd apps/web && pnpm build` 成功（无 TS 错误）。
- [ ] AC2：`pnpm lint` 通过；`pnpm test` 通过（至少 1 个用例）。
- [ ] AC3：`pnpm dev` 启动后页面可见：白色背景、直角卡片、无阴影；ECharts 示例折线图渲染。
- [ ] AC4：全局 CSS 中 border-radius 均为 0、无 box-shadow；检查 build 产物无组件库样式混入。

## 6. 测试计划

- 单元：App 渲染测试（vitest + testing-library 或最小渲染断言）。
- 手动：dev 启动目检 UI 规范（白底、直角、无阴影、图表渲染）。

## 7. 里程碑与估算

| 子任务 | 预估 |
|---|---|
| Vite 工程初始化 | 10 分钟 |
| 全局样式 + 基础页面 | 15 分钟 |
| ECharts 示例图 | 15 分钟 |
| lint/test/build 通过 | 15 分钟 |

## 8. 风险与对策

| 风险 | 对策 |
|---|---|
| echarts 全量引入导致产物体积大 | 按需引入（core + 组件注册） |
| 模板自带样式违反 UI 规范 | 用 Vite 模板后全部样式重写，不残留默认 Vite 样式 |

## 9. 变更记录

| 日期 | 变更内容 | 理由 |
|---|---|---|
| 2026-08-19 | 初始定稿 | — |
| 2026-08-19 | 验收通过：lint/test/build 全过；DOM 计算样式验证 radius=0、shadow=none、纯白背景；ECharts canvas 渲染成功 | 阶段 A3 完成 |
