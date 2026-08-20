# OpenCode Go Pool — 前端监控台

React + Vite + TypeScript + ECharts 实现的账号状态大盘：账号卡片、用量趋势图、统一事件时间线。

## 技术栈

- React 19 + TypeScript（strict）
- Vite 7（构建/dev server）
- ECharts 6（按需引入：bar/line/grid/tooltip/legend，拆 chunk 控制体积）
- Vitest + Testing Library（单元测试）
- ESLint 9（typescript-eslint flat config）

## 脚本命令

```bash
pnpm install     # 安装依赖（Node 24 + pnpm 11）
pnpm dev         # 开发服务器 http://localhost:48701（/api 代理到后端 48700）
pnpm build       # 类型检查 + 生产构建
pnpm lint        # ESLint
pnpm test        # Vitest 单次运行
pnpm preview     # 预览生产构建
```

## UI 设计规范（强制）

白色简洁风，全站统一：

- 背景纯白（`#FFFFFF`），正文深灰（`#1F2937`），边框浅灰（`#E5E7EB`）细线；
- **禁止阴影**：任何元素不用 box-shadow / drop-shadow；
- **禁止圆角**：所有 border-radius 一律 0（直角）；
- 强调色单一（`#2563EB`）；语义状态色仅绿（健康）/ 橙（冷却）/ 红（禁用）。

设计 token 定义在 `src/index.css`（`:root` CSS 变量）。

## 目录结构

```
apps/web/src/
├─ main.tsx / App.tsx          # 入口与单页容器（页头 + Dashboard）
├─ index.css                   # 全局设计 token 与基础样式
├─ types/pool.ts               # 后端响应类型（AccountStatus / Stats / EventItem）
├─ services/api.ts             # API 客户端（accounts / stats / events）
├─ features/
│  ├─ dashboard/               # 大盘：统计摘要、账号卡片、状态徽章、轮询 hook
│  └─ charts/                  # 用量趋势图（ECharts）与统一事件时间线
└─ test/                       # 测试设置与 App 测试
```

## 数据流

`useAccountPolling`（10s 轮询）→ `Promise.all` 拉取 `/api/accounts` + `/api/stats` + `/api/events` → UsagePanel 组装渲染；后端不可用时保留上次数据并显示警告（不清空 UI）。
