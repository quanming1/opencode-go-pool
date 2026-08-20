# PRD-C3-分Tab管理与网关鉴权

> 状态生命周期：草稿 → 评审 → approved（定稿）→ 开发中 → 已验收

## 元信息

| 字段 | 值 |
|---|---|
| 阶段 | C3 |
| 名称 | 分 Tab 管理（用量信息 / API Key 管理）+ 网关鉴权 |
| 状态 | approved |
| 创建日期 | 2026-08-20 |
| 定稿日期 | 2026-08-20 |
| 验收日期 | — |
| 关联文档 | docs/TODO.yaml 阶段 C3；PRD-B1（账号池）、PRD-C1/C2（前端大盘） |

## 1. 背景与目标

- **背景**：监控台目前是单页纵排（账号卡 → 趋势图 → 时间线），功能堆叠不利于扩展；转发端点无鉴权（任意调用方可用）；账号控制（禁用/清冷却）只能改数据库或等 5 小时。
- **额度查询说明**：OpenCode Go 无公开额度 API，Dashboard 数据需浏览器 cookie 抓取（脆弱且越合规边界），**明确不做**。用量数据源 = 本地转发统计（B2/C2 已建）。
- **目标**：
  1. 前端重构为左右分栏 Tab 布局：左侧 tab 导航，右侧内容区；
  2. Tab1「用量信息」：每账号卡（状态/请求/token/错误）+ **控制按钮**（清除冷却、启用/禁用）+ 汇总统计（总量/错误/趋势图/轮换时间线并入）；
  3. Tab2「API Key 管理」：为网关生成/吊销访问 key；转发端点启用 Bearer 鉴权。
- **非目标**：不做额度/余额查询（cookie 抓取不做）；不做多用户/角色权限（单管理员）；不做 key 用量限额/过期策略（后续可加）；不做 Tab 路由持久化（内存态切换即可）。

## 2. 需求范围

### 2.1 功能需求

**后端**

- [ ] FR1：网关 key 存储：SQLite 新表 `gateway_keys`（id / key_hash / label / created_at / revoked_at），key 只存 SHA-256 哈希，明文仅在创建时返回一次。
- [ ] FR2：master key：`.env.keys` 可配 `GATEWAY_MASTER_KEY`（可选）；master key 与库内 key 等效，不落库。
- [ ] FR3：key 管理 API（管理端点挂 `/api/keys`，需 master key 或任一有效网关 key 鉴权）：
  - `GET /api/keys`：列表（id/label/created_at/revoked_at，无哈希）；
  - `POST /api/keys`：`{label}` → 生成 `gk-` 前缀 key，返回明文一次；
  - `DELETE /api/keys/{id}`：吊销（软删，revoked_at 置时间）。
- [ ] FR4：转发端点鉴权：`/api/v1/responses`、`/api/v1/chat/completions`、`/api/v1/models` 要求 `Authorization: Bearer <key>`；无效/吊销 → 401；**未配置任何 key 且无 master key 时放行**（向后兼容本地裸跑）。
- [ ] FR5：账号控制 API（管理端点需鉴权，同 FR3）：
  - `POST /api/accounts/{id}/clear`：清除冷却/错误计数 → healthy；
  - `POST /api/accounts/{id}/enable` / `POST /api/accounts/{id}/disable`。
- [ ] FR6：管理鉴权中间件：`/api/keys*`、`/api/accounts/*`（写操作）需要 `Authorization: Bearer` 有效 key；读端点 `/api/accounts`（GET）、`/api/stats`、`/api/switch-history`、`/health` 保持开放（监控台轮询用，本机部署）。

**前端**

- [ ] FR7：左右分栏布局：左侧竖排 tab 导航（固定宽，直角边框），右侧内容区；页面级样式沿用白色简洁规范。
- [ ] FR8：Tab1「用量信息」：
  - 汇总卡（总请求/总 token/总错误）；
  - 账号卡列表：现有字段 + 每卡三个操作按钮「清除冷却」（cooldown 时可用）「禁用/启用」（状态切换）；
  - 用量趋势图 + 轮换时间线（现有组件迁入本 tab）。
- [ ] FR9：Tab2「API Key 管理」：
  - key 列表（label/创建时间/状态：有效/已吊销）；
  - 「生成新 key」表单（label 输入）→ 弹出明文 key 一次展示 + 复制按钮；
  - 「吊销」按钮（二次确认）；
  - 鉴权状态提示：后端未启用鉴权（无 key 且无 master）时顶部显示「鉴权未启用」警示条。
- [ ] FR10：操作反馈：按钮请求中禁用、成功/失败 toast 或行内提示；账号操作后立即刷新列表。

### 2.2 非功能需求

- 安全：key 哈希存储；明文不落日志；吊销立即生效（内存缓存随请求校验 DB 或每次查库，量小直接查库）。
- 兼容：无 key 配置时一切端点行为与现状一致（不破坏现有 curl 示例与测试）。
- 可测：鉴权中间件、key CRUD、账号控制全部 pytest；前端组件 vitest（mock API）。

## 3. 技术方案

- 后端新增：
```
apps/backend/src/opencode_pool/
├─ auth/
│  ├─ __init__.py
│  └─ gateway_key.py     # KeyManager：哈希/生成/校验/吊销（依赖 AccountStore 同库）
└─ api/
   ├─ keys.py            # /api/keys CRUD 路由
   └─ auth.py            # Bearer 校验依赖（FastAPI Depends）
```
- store 扩展：`gateway_keys` 表 + save/list/revoke/verify（verify 走哈希比对）。
- 路由改动：proxy/router.py 三个端点加 `Depends(require_gateway_key)`；accounts.py 扩控制端点；keys.py 挂载。
- 前端结构：
```
apps/web/src/
├─ App.tsx                    # 左右分栏：Sidebar（tab 导航）+ 内容区
├─ components/Sidebar.tsx     # 左侧 tab
├─ features/usage/            # Tab1（迁入 dashboard 组件 + AccountControls）
│  └─ AccountControls.tsx     # 清除冷却/启用/禁用按钮组
└─ features/keys/             # Tab2
   ├─ KeysPanel.tsx / KeyCreateForm.tsx / KeyList.tsx
```
- 轮询策略：Tab 激活时轮询对应数据（accounts/stats 常轮；keys 进 tab 时拉一次 + 操作后刷新）。

## 4. 接口定义

- `POST /api/keys` body `{"label": "ftre"}` → `{"id": 1, "label": "ftre", "key": "gk-xxxx...", "created_at": "..."}`
- `GET /api/keys` → `{"keys": [{"id": 1, "label": "ftre", "created_at": "...", "revoked_at": null}]}`
- `DELETE /api/keys/1` → `{"ok": true}`
- `POST /api/accounts/a1/clear` → `{"ok": true, "status": "healthy"}`
- `POST /api/accounts/a1/disable` / `enable` → `{"ok": true, "status": "disabled"/"healthy"}`
- 转发端点 401 体：`{"error": {"message": "invalid or missing gateway key"}}`
- 鉴权头：`Authorization: Bearer gk-xxx` 或 master key。

## 5. 验收标准

- [ ] AC1：后端 pytest 全绿（新增 keys/auth/控制端点测试 ≥ 10 个）；ruff 无警告。
- [ ] AC2：无 key 配置时转发端点照常可用（兼容模式）；配置后无 Bearer → 401，有效 key → 200，吊销后 → 401。
- [ ] AC3：POST /api/keys 生成 gk- key 且列表可见；DELETE 后列表显示已吊销且校验失败。
- [ ] AC4：POST /api/accounts/{id}/clear 把 cooldown 账号恢复 healthy；disable/enable 生效且 pick_next 跳过禁用账号。
- [ ] AC5：前端 vitest/build 全过；左右分栏 + 两 tab 切换正常。
- [ ] AC6：Tab1：控制按钮点击后账号卡状态即时变化（清冷却→健康）；Tab2：生成 key 明文一次性展示可复制、吊销有确认。
- [ ] AC7：UI 规范：白色简洁、直角、无阴影（沿用既有 token）。
- [ ] AC8：端到端实测：生成 key → 用 key curl 转发 200 → 吊销 → 401。

## 6. 测试计划

- 后端：KeyManager 单测（哈希往返/校验/吊销）；API 集成（keys CRUD + 各端点 401/200 矩阵）；账号控制（clear/enable/disable + pool 状态断言）；兼容模式（无 key 放行）。
- 前端：Sidebar tab 切换；AccountControls 调 API（mock）；KeysPanel 列表/生成/吊销交互（mock）；鉴权警示条条件渲染。
- 手动：AC8 全链路 curl。

## 7. 里程碑与估算

| 子任务 | 预估 |
|---|---|
| 后端 auth + keys API + 鉴权接线 | 45 分钟 |
| 后端账号控制 API | 20 分钟 |
| 后端测试 | 35 分钟 |
| 前端分栏 + Tab1 迁移 + 控制按钮 | 40 分钟 |
| 前端 Tab2 key 管理 | 35 分钟 |
| 前端测试 + 端到端 | 35 分钟 |

## 8. 风险与对策

| 风险 | 对策 |
|---|---|
| 现有测试因新增鉴权失败 | 鉴权默认关闭（无 key 即放行），测试环境不配 key |
| 明文 key 只显示一次，用户没复制 | 创建弹窗不关闭不允许离开（前端强制确认） |
| SQLite 并发读写（校验频繁） | 单实例 + WAL，量级小；校验失败不缓存 |
| 前端重构破坏现有组件 | dashboard 组件平移到 features/usage，props 不变 |

## 9. 变更记录

| 日期 | 变更内容 | 理由 |
|---|---|---|
| 2026-08-20 | 初始定稿（原方案含额度查询，因 OpenCode 无公开 API 且 cookie 抓取越合规边界而移除） | 用户决策：不做额度查询，用量数据源定为本地统计 |
