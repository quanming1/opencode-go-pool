# PRD-C5-账号额度展示

> 状态生命周期：草稿 → 评审 → approved（定稿）→ 开发中 → 已验收

## 元信息

| 字段 | 值 |
|---|---|
| 阶段 | C5 |
| 名称 | 账号额度展示 |
| 状态 | 已验收 |
| 创建日期 | 2026-08-20 |
| 定稿日期 | 2026-08-20 |
| 验收日期 | 2026-08-20 |
| 关联文档 | docs/TODO.yaml 阶段 C5；PRD-C1（大盘）/ PRD-C3（Tab 管理）遗留需求重启 |

## 1. 背景与目标

### 背景

C3 阶段规划「每个 KEY 的滚动/周/月用量 + 总额度」展示时，调研结论是 OpenCode Go
无公开额度查询接口（QuotaHub 需浏览器 cookie 抓 dashboard HTML，越合规边界），该需求被搁置。

2026-08-20 实测确认：**OpenCode 官方额度接口已上线**，普通 API key 即可查询，
无需 cookie、无需 workspace id：

```
GET https://opencode.ai/zen/go/v1/usage
Authorization: Bearer <OPENCODE_GO_API_KEY>

200 OK
{
  "usage": {
    "rolling":  {"status": "ok",           "percent": 0,   "resetsAt": "2026-08-20T14:09:31Z"},
    "weekly":   {"status": "rate-limited", "percent": 100, "resetsAt": "2026-08-24T00:00:00Z"},
    "monthly":  {"status": "ok",           "percent": 50,  "resetsAt": "2026-09-19T05:54:29Z"}
  }
}
```

三个窗口对应 OpenCode Go 订阅的三层限额（美元计价）：滚动 5 小时窗口 $12、
每周 $30、每月 $60。`percent` 为**已用百分比**；`status=rate-limited` 表示该窗口
已用满（此时 percent=100，账号会被上游 429 拒绝直至 resetsAt）。

### 目标

监控台「用量信息」Tab 补齐额度维度：每个账号卡片展示滚动/周/月三个窗口的
已用百分比与重置倒计时，汇总卡展示全池额度总览（可用账号数、各窗口平均用量）。

### 非目标

- 不实现额度数据的历史存储/趋势图（当前值展示即可，趋势仍由本地统计 /api/stats 承担）；
- 不做基于额度的智能调度（如优先选用量低的账号）——调度仍按 healthy 状态机轮换；
- 额度查询为只读操作，不产生统一事件（C4 事件流不新增类型）；
- 不解析/存储美元绝对值（上游只给百分比，绝对额度仅作为文档说明）。

## 2. 需求范围

### 2.1 功能需求

- [ ] FR1 额度查询服务：新增 `quota` 模块，对账号池内所有 `enabled` 账号并发调用
  `{account.base_url}/usage`（Authorization: Bearer 账号密钥），解析 rolling/weekly/monthly
  三窗口；单账号失败（网络/4xx/解析异常）不影响其他账号，该账号返回 `quota: null` + `error` 摘要。
- [ ] FR2 TTL 缓存：服务端缓存额度结果，默认 60 秒（`QUOTA_CACHE_TTL_SECONDS`）；
- [ ] FR6 额度总览卡：SummaryCards 新增第 4 张卡「总额度」：
  - 总分配额度：滚动 `$12 × enabled 账号数`、每周 `$30 × enabled 账号数`、每月 `$60 × enabled 账号数`；
  - 估算已用：仅对查询成功账号按 `percent × 单账号计划上限` 折算并求和，标注「估算已用」而不是精确账单；
  - 同时保留可用额度账号 `rolling status=ok / queried` 与三个窗口平均已用百分比；查询失败账号不计入估算已用，但仍计入总分配额度。
  - 当前 OpenCode Go 计划上限常量来自官方文档/实测语义：rolling=$12、weekly=$30、monthly=$60；代码集中定义，未来计划变化只改一处。
- [ ] FR7 手动刷新：UsagePanel 额度区提供「刷新额度」按钮，调 `GET /api/quota?refresh=1`
  强制重新查询；按钮请求期间显示加载态，失败提示错误（保留上次数据）。
- [ ] FR8 配置项：`QUOTA_CACHE_TTL_SECONDS`（默认 60）、`QUOTA_TIMEOUT_SECONDS`
  （默认 10，单账号额度请求超时）写入 `.env.example` 与 README 配置表。
  可用额度账号 X/N（rolling 窗口 status=ok 的账号数 / 已查询账号数）、
  滚动均值 P%、周均值 P%、月均值 P%（参与账号 = 查询成功的账号）。
- [ ] FR7 手动刷新：UsagePanel 额度区提供「刷新额度」按钮，调 `GET /api/quota?refresh=1`
  强制重新查询；按钮请求期间显示加载态，失败提示错误（保留上次数据）。
- [ ] FR8 配置项：`QUOTA_CACHE_TTL_SECONDS`（默认 60）、`QUOTA_TIMEOUT_SECONDS`
  （默认 10，单账号额度请求超时）写入 `.env.example` 与 README 配置表。

### 2.2 非功能需求

- 性能：6 账号并发查询，整体接口耗时 ≤ 单账号超时上限（10s）；缓存命中 < 10ms。
- 安全：额度响应绝不包含 api_key；错误摘要截断且复用现有脱敏原则（_safe_detail 模式）。
- 兼容性：额度接口失败完全降级（前端显示「额度未知」），不影响账号池/转发/统计任何既有功能。
- 上游友好：TTL 缓存防高频；仅 enabled 账号发起查询（disabled 不浪费上游调用）。

## 3. 技术方案

### 3.1 后端模块设计

```
apps/backend/src/opencode_pool/quota/
├─ __init__.py          # 导出 QuotaService
└─ service.py           # QuotaService：并发查询 + TTL 缓存 + 降级
apps/backend/src/opencode_pool/api/quota.py   # GET /api/quota 路由
```

关键数据结构（service 内部 → API 响应）：

```python
# 单窗口
{"status": "ok", "percent": 50, "resets_at": "2026-09-19T05:54:29Z", "resets_in_seconds": 1234}
# 单账号
{"account_id": "opencode-go-1", "quota": {"rolling": {...}, "weekly": {...}, "monthly": {...}} | None, "error": None | "摘要"}
# 全池响应
{
  "accounts": [单账号...],
  "summary": {
    "total_accounts": 6,          # enabled 账号总数
    "queried": 6,                 # 本次实际查询数
    "ok_accounts": 6,             # 查询成功数
    "rolling_available": 4,       # rolling status=ok 的账号数
    "rolling_avg_percent": 12,    # 查询成功账号的滚动均值（int，四舍五入）
    "weekly_avg_percent": 65,
    "monthly_avg_percent": 40
  },
  "fetched_at": "2026-08-20T09:00:00+00:00",   # 本次（或缓存对应）取数时间 UTC
  "cached": true                   # 本次响应是否命中缓存
}
```

实现要点：

- QuotaService 持有 `pool`（取账号与密钥）、`client: httpx.AsyncClient`（超时
  QUOTA_TIMEOUT_SECONDS）、`_cache`（fetched_at + accounts + summary）与 `asyncio.Lock`
  防并发击穿（缓存过期时只允许一个请求打上游，其余等待复用）。
- 解析容错：上游响应缺 `usage` 或某窗口缺失 → 该窗口按未知处理（整个账号 quota=null
  + error="响应缺少 usage 字段"）；`percent` 非数字 → 按未知处理。
- 端点地址 = `account.base_url.rstrip("/") + "/usage"`（账号未配 base_url 时用全局
  upstream_base_url），与转发端点同源无需新配置。

### 3.2 API 路由

- `GET /api/quota?refresh=0|1`：读端点，与 /api/stats 同级开放（本地单用户模式）；
  `refresh=1` 等价于「强制刷新缓存」。

### 3.3 前端设计

```
apps/web/src/types/pool.ts        # QuotaWindow / AccountQuota / QuotaSummary / QuotaResponse
apps/web/src/services/api.ts      # fetchQuota(force?)
apps/web/src/features/dashboard/useAccountPolling.ts   # Promise.all 追加 fetchQuota()（非强制）
apps/web/src/features/dashboard/AccountCard.tsx        # quota 可选 prop + 额度区块
apps/web/src/features/dashboard/SummaryCards.tsx       # 第 4 张「额度总览」卡
apps/web/src/features/dashboard/quotaFormat.ts         # resetsInText(seconds) 倒计时文案（纯函数）
apps/web/src/features/usage/UsagePanel.tsx             # 「刷新额度」按钮（force + busy 态）
```

倒计时文案规则（对齐用户控制台原话「99% 重置于 57 分钟」「3 天 18 小时」「30 天 0 小时」）：

- < 1 小时：`X 分钟`（0 → 「即将重置」）
- < 1 天：`X 小时 Y 分钟`
- ≥ 1 天：`X 天 Y 小时`

进度条：宽 `percent%` 的 div；`rate-limited`（或 percent ≥ 100）用 danger 色，
percent ≥ 80 用 warn 色，其余用 ok 色；符合白色简洁规范（无圆角无阴影）。

## 4. 接口定义

### GET /api/quota

```bash
# 常规（命中服务端缓存时不访问上游）
curl http://127.0.0.1:48700/api/quota
# 强制刷新
curl "http://127.0.0.1:48700/api/quota?refresh=1"
```

单账号响应项：

```json
{
  "account_id": "opencode-go-1",
  "quota": {
    "rolling": {
      "status": "ok",
      "percent": 2,
      "resets_at": "2026-08-20T14:09:31Z",
      "resets_in_seconds": 3431
    },
    "weekly": {
      "status": "ok",
      "percent": 74,
      "resets_at": "2026-08-24T00:00:00Z",
      "resets_in_seconds": 338400
    },
    "monthly": {
      "status": "ok",
      "percent": 44,
      "resets_at": "2026-09-19T05:54:29Z",
      "resets_in_seconds": 2598836
    }
  },
  "error": null
}
```

全池响应：

```json
{
  "accounts": [
    {"account_id": "opencode-go-1", "quota": {"rolling": {}, "weekly": {}, "monthly": {}}, "error": null},
    {"account_id": "opencode-go-2", "quota": null, "error": "http 401"}
  ],
  "summary": {
    "total_accounts": 6,
    "queried": 6,
    "ok_accounts": 5,
    "rolling_available": 5,
    "rolling_avg_percent": 18,
    "weekly_avg_percent": 60,
    "monthly_avg_percent": 42,
    "allocated_usd": {"rolling": 72, "weekly": 180, "monthly": 360},
    "estimated_used_usd": {"rolling": 8, "weekly": 117, "monthly": 144}
  },
  "fetched_at": "2026-08-20T09:00:00+00:00",
  "cached": false
}
```

字段口径：`percent` 是上游返回的已用百分比；`allocated_usd` 是 enabled 账号数乘以
单账号 Go 计划窗口上限；`estimated_used_usd` 仅按百分比折算，是近似展示，不代表精确账单。
额度查询失败的账号仍计入 `allocated_usd`，但不计入 `ok_accounts`、均值与 `estimated_used_usd`。

### 配置（.env 新增）

| 变量 | 默认值 | 说明 |
|---|---|---|
| `QUOTA_CACHE_TTL_SECONDS` | 60 | 额度结果缓存秒数（缓存期内不打上游） |
| `QUOTA_TIMEOUT_SECONDS` | 10 | 单账号额度请求超时 |

## 5. 验收标准

- [x] AC1：`pytest` 全绿（123 passed）——quota service 单测覆盖：正常解析（三窗口+倒计时）、TTL 缓存命中
  （第二次调用 mock transport 计数为 1 轮）、force 刷新、单账号 401 降级（quota=null + error，
  其余账号正常）、summary 均值/available/总分配额度/估算已用计算、异常响应缺 usage 字段降级。
- [x] AC2：`GET /api/quota` 集成测试：fake upstream 返回固定 usage，断言响应结构
  （accounts/summary/fetched_at/cached）与脱敏（无 sk- 明文）。
- [x] AC3：真实上游实测通过：本机 6 账号 `GET /api/quota?refresh=1` 全部返回真实百分比与重置时间
  （go-1 周窗口 100% rate-limited、go-2 滚动窗口 100% rate-limited，与官方控制台一致）；
  `cached=false` → 立即再查 `cached=true` 且 fetched_at 不变。
- [x] AC4：前端 vitest 全绿（31 passed）——AccountCard 额度区块（三窗口行 + rate-limited 标红 + 无数据显示额度未知）、
  SummaryCards 额度总览卡（总分配额度/估算已用美元、X/N 与均值）、quotaFormat 倒计时文案三分段。
- [x] AC5：UsagePanel「刷新额度」按钮实测：网络面板确认走 `?refresh=1`（200 OK），
  busy 态与失败保留旧数据由 hook 测试覆盖。
- [x] AC6：UI 目检通过（Playwright DOM 断言）：额度区块/进度条/汇总卡 borderRadius=0、
  boxShadow=none 零违规；rate-limited 窗口红色进度条 2 处与 API 实测一致。
- [x] AC7：`ruff` 0 告警；前端 `eslint` 0 告警、`build` 成功。
- [x] AC8：文档同步完成——README API 表加 /api/quota、配置表加两个新变量、docs/usage.md 3.4/3.5 更新、
  后端 README 模块表加 quota。

## 6. 测试计划

- 单元（后端 test_quota.py / test_quota_api.py）：httpx.MockTransport 伪造 usage 响应；
  缓存计数用自定义 handler 调用次数断言；时间相关用 monkeypatch 固定 now。
- 单元（前端）：quotaFormat 纯函数三分段；AccountCard/SummaryCards 渲染断言（含空数据）。
- 手动：真实额度接口拉取 + 刷新按钮 + 禁用某账号后其不再被查询。

## 7. 里程碑与估算

| 子任务 | 预估 |
|---|---|
| 后端 quota 模块 + API + 单测 | 1.5h |
| 前端类型/卡片/汇总/按钮 + 测试 | 1.5h |
| 真实接口实测 + 文档 + 收尾三联动 | 0.5h |

## 8. 风险与对策

| 风险 | 对策 |
|---|---|
| 上游 usage 接口为非官方承诺接口，未来可能变动 | 解析层完全容错（缺字段/类型不符一律降级为未知），不崩溃不阻塞主路径 |
| 高频轮询打爆上游 | 服务端 TTL 缓存 + Lock 防击穿；前端仅手动按钮才 force |
| 额度查询拖慢大盘首屏 | 并发查询 + 10s 超时；失败即时降级显示未知 |
| percent 语义误读（已用 vs 剩余） | 以实测为准（rate-limited 时=100），文案统一「已用 X%」 |

| 日期 | 变更内容 | 理由 |
|---|---|---|
| 2026-08-20 | 初始定稿：官方额度接口（GET /zen/go/v1/usage）实测可用，重启 C3 搁置的额度展示需求 | 知乎文章（zhuanlan.zhihu.com/p/2073771274376056874）指出接口已上线，本机 6 key 实测 200 OK 确认 |
| 2026-08-20 | 扩展 FR6：总览新增滚动/周/月总分配额度与按百分比折算的估算已用美元，并在 API summary 中返回 allocated_usd/estimated_used_usd | 用户明确要求展示每个 key 额度以及多个 key 合计总额度；上游只提供百分比，必须明确标注估算口径 |