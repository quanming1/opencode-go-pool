# PRD-C1-前端账号状态大盘

> 状态生命周期：草稿 → 评审 → approved（定稿）→ 开发中 → 已验收

## 元信息

| 字段 | 值 |
|---|---|
| 阶段 | C1 |
| 名称 | 前端账号状态大盘 |
| 状态 | 已验收 |
| 创建日期 | 2026-08-19 |
| 定稿日期 | 2026-08-19 |
| 验收日期 | 2026-08-20 |
| 关联文档 | docs/TODO.yaml 阶段 C1；docs/prd/PRD-B1-accounts-pool.md（数据来源 /api/accounts） |

## 1. 背景与目标

- **背景**：后端 B1-B4 已提供 `GET /api/accounts`（账号脱敏状态）与切换历史（SQLite 落库）。前端目前是 A3 骨架（单页 + 示例折线图），需要把账号池状态可视化，让运维一眼看清哪些账号健康/冷却/禁用。
- **目标**：前端首页成为**账号状态大盘**：显示账号卡片列表（含状态徽章）、状态统计摘要（可用/冷却/禁用计数），支持定时自动刷新；保留白色简洁风格（无阴影、无圆角）。
- **非目标**：不做用量趋势图（C2）；不做切换事件时间线（C2）；不做路由/多页面（单页）；不做鉴权（本机单用户）；不做编辑账号（改配置重启）。

## 2. 需求范围

### 2.1 功能需求

- [ ] FR1：数据获取：前端从 `GET /api/accounts` 拉取账号列表（开发期经 Vite proxy `/api` → 48700）。
- [ ] FR2：账号卡片列表：每账号一张卡片，显示 `name` / `id` / `status` / `enabled` / `consecutive_failures` / `error_count` / `last_error`（若有）/ `cooldown_seconds_remaining`（冷却中显示剩余秒）；`api_key` 绝不出现在 UI（后端已脱敏，前端不做任何处理）。
- [ ] FR3：状态徽章：按 status 显示不同样式的徽章——`healthy` 绿色、`cooldown` 橙色、`disabled` 红色；禁用（enabled=false）灰化整卡。
- [ ] FR4：统计摘要：顶部三条统计卡——`可用`（healthy 且 enabled）、`冷却中`（cooldown）、`已禁用`（disabled）。
- [ ] FR5：自动刷新：每 10 秒轮询 `/api/accounts`；首次加载显示 loading；网络/后端错误显示错误态（非崩溃）。
- [ ] FR6：UI 规范：严格白色简洁风（复用 index.css 的设计 token：白底、直角、无阴影、细线边框）；无第三方 UI 库。

### 2.2 非功能需求

- 可维护性：把 API 客户端、hooks、组件分层；类型定义与后端响应结构对应。
- 可测：组件用 mock 数据可单测（vitest）；轮询逻辑可注入 interval 以便测试。
- 兼容性：默认 polling；不引入状态管理库（本轮用 React 内置 + 简单 hook）。

## 3. 技术方案

- 目录新增（替换 demo）：

```
apps/web/src/
├─ services/api.ts           # fetchJson GET /api/accounts（+ C2 的 /api/stats 预留同文件）
├─ types/pool.ts             # AccountStatus / PoolAccount / AccountsResponse 类型
├─ features/dashboard/
│  ├─ Dashboard.tsx          # 容器：数据获取 + 轮询 + 组装
│  ├─ StatusBadge.tsx        # 状态徽章
│  ├─ SummaryCards.tsx       # 统计摘要卡
│  ├─ AccountCard.tsx        # 单账号卡片
│  └─ useAccountPolling.ts   # 轮询 hook
├─ features/dashboard/dashboard.css  # 大盘样式（白色简洁）
└─ features/demo/             # 删除
```

- `App.tsx` 改为渲染 `Dashboard`；保留页头（项目名 + 版本）。
- 样式：在 index.css 已有 token 基础上，dashboard.css 只加布局与徽章色（绿/橙/红，低饱和）。
- 轮询 hook：

```ts
function useAccountPolling(intervalMs = 10_000) {
  const [accounts, setAccounts] = useState<PoolAccount[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let on = true;
    async function tick() {
      try {
        const data = await fetchAccounts();
        if (on) { setAccounts(data); setError(null); setLoading(false); }
      } catch (e) {
        if (on) setError(String(e));
      } finally {
        if (on) timer = setTimeout(tick, intervalMs);
      }
    }
    let timer: number;
    tick();
    return () => { on = false; clearTimeout(timer); };
  }, [intervalMs]);
  return { accounts, error, loading };
}
```

## 4. 接口定义

- 消费 `GET /api/accounts`：

```json
{
  "accounts": [
    {
      "id": "opencode-go-1",
      "name": "主账号",
      "status": "healthy",
      "cooldown_until": null,
      "cooldown_seconds_remaining": null,
      "last_error": null,
      "error_count": 0,
      "consecutive_failures": 0,
      "enabled": true
    }
  ]
}
```

- 类型（TypeScript）：

```ts
export type AccountStatus = "healthy" | "cooldown" | "disabled";
export interface PoolAccount {
  id: string;
  name: string;
  status: AccountStatus;
  cooldown_until: string | null;
  cooldown_seconds_remaining: number | null;
  last_error: string | null;
  error_count: number;
  consecutive_failures: number;
  enabled: boolean;
}
```

## 5. 验收标准

- [ ] AC1：`cd apps/web && pnpm lint && pnpm test && pnpm build` 全过（含新增 dashboard 测试）。
- [ ] AC2：启动前后端后首页显示账号卡片与统计摘要；无账号时显示"无账号"空态。
- [ ] AC3：状态徽章颜色随 status 变化（healthy 绿 / cooldown 橙 / disabled 红）；禁用卡灰化。
- [ ] AC4：轮询每 10s 刷新；后端停止时页面显示错误态不清空已加载数据（或显示上次数据 + 警告）。
- [ ] AC5：UI 目检（Playwright/DOM）：背景白、卡片直角（border-radius 0）、无阴影、无 demo 残留。
- [ ] AC6：代码无 `api_key` 相关处理；`grep` 前端无明文密钥引用。

## 6. 测试计划

- vitest：`SummaryCards` 计数正确；`StatusBadge` 各状态类名/文案；`useAccountPolling` 注入短 interval 验证轮询与错误路径（mock fetch）；`Dashboard` 空态。
- 手动/playwright：起后端（空账号 + 带账号各一次）目检 UI；检查计算样式。

## 7. 里程碑与估算

| 子任务 | 预估 |
|---|---|
| types + api.ts + polling hook | 20 分钟 |
| SummaryCards / StatusBadge / AccountCard | 25 分钟 |
| Dashboard 容器 + App 接线 + 样式 | 20 分钟 |
| vitest + 目检 | 25 分钟 |

## 8. 风险与对策

| 风险 | 对策 |
|---|---|
| 轮询泄漏/竞态 | hook 里 on 标志 + cleanup 清 timer |
| 后端未启动 | error 态展示 + 保留上次数据 |
| demo 残留样式混入 | 删除 demo 目录，grep 确认 |
| echarts 不再使用 | A3 的 echarts 在 C2 用，C1 不引入 |

## 9. 变更记录

| 日期 | 变更内容 | 理由 |
|---|---|---|
| 2026-08-19 | 初始定稿 | — |
| 2026-08-20 | 验收通过：vitest 10 passed、build 成功、UI 目检（直角 0px/无阴影/白底/健康绿徽章/2 账号卡）；删除 demo 占位 | 阶段 C1 完成 |
