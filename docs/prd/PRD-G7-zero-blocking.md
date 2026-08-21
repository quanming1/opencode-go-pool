# PRD-G7-速度对齐直连·转发热路径零阻塞改造

> 状态生命周期：草稿 → 评审 → approved（定稿）→ 开发中 → 已验收

## 元信息

| 字段 | 值 |
|---|---|
| 阶段 | G7 |
| 名称 | 速度对齐直连 · 转发热路径零阻塞改造 |
| 状态 | approved |
| 创建日期 | 2026-08-21 |
| 定稿日期 | 2026-08-21 |
| 验收日期 | — |
| 关联文档 | docs/TODO.yaml 阶段 G7；apps/backend/src/opencode_pool/store/；apps/backend/src/opencode_pool/events/recorder.py；apps/backend/src/opencode_pool/usage/recorder.py；apps/backend/src/opencode_pool/api/；apps/backend/src/opencode_pool/app.py；apps/backend/src/opencode_pool/proxy/forwarder.py |

## 1. 背景与目标

- **背景**：用户要求「和直连保持一样的速度」。上一轮（fix(B2)）已消除每请求 TLS 握手与首 chunk 前同步落库，实测首 chunk 中位数 2493→2207ms，但与直连（约 1994ms）仍差约 200ms。取证分析确认剩余差距来自**转发热路径的同步 IO 与事件循环争抢**：
  1. 每次请求的 `usage.record`（写 usage_events）与 `event.record`（写 events）仍是**事件循环内同步 SQLite 写**（流式虽已推迟到流结束，但下一个请求/其他并发请求会被阻塞）；
  2. 监控台每 10s 轮询 `/api/stats` 的 `aggregate_usage` + `events_summary` 是**同步聚合查询**（数十 ms 级 sqlite 计算 + JSON），运行在事件循环上——流式转发期间插入即造成 chunk 抖动；
  3. `/api/events` 分页查询、`/api/logs/overview` 聚合也是同步查询，同样占用事件循环。
  4. 已排除：`AccountPool.record_success` 健康常态零落库（仅失败恢复时 `_persist`，低频，保留同步语义）。
- **目标**：转发热路径（forward → 上游 → 回传）**零同步 IO**——落库完全移出事件循环（单写线程队列），读路径移出事件循环（`asyncio.to_thread`）+ 统计结果 TTL 缓存；出站尝试 HTTP/2 多路复用。验收口径：直连 vs 优化后池子多轮交替基准，首 chunk **中位数差 ≤ 50ms**（本地开销趋近物理下限）。
- **非目标**：不换语言（I/O 密集转发，语言无关，已证）；不动前端轮询频率（后端消化后 10s 轮询不再阻塞转发）；不改选号策略（账号响应差异属上游噪声，噪声由多轮交替基准均摊）；不引入新依赖（队列用标准库 `queue`/`threading`/`asyncio.to_thread`）。

## 2. 摸底结论（已执行）

- 热路径每请求同步 IO：1 次 `save_usage` + 1 次 `save_event`（含 commit）。
- 轮询路径同步查询：`aggregate_usage`（GROUP BY 小时桶）+ `events_summary`（近 500 条事件 JSON 解析 + 耗时排序/p95）——测试环境实测单次 10-50ms，会阻塞事件循环。
- `record_success`：仅连续失败计数非 0 时 `_persist`（低频），健康常态纯内存。
- 唯一 SQLite 连接（`check_same_thread=False` + WAL）：单写线程独占写、读可走第二连接（WAL 读写并发）或同一连接串行——**写队列用专用写线程 + 原连接独占；读仍在主连接，经 `to_thread` 后与写线程分属不同线程仍会竞争同一连接**——解决：读路径统一走 `asyncio.to_thread` 且 SQLite 连接设置 `check_same_thread=False` 支持跨线程串行访问（GIL 保证单连接并发安全由 sqlite3 模块内部门锁处理）。

## 3. 需求范围

### 3.1 功能需求

- [ ] FR1：新建 `store/writer.py`——`SQLiteWriter`：
  - `submit(fn, *args)`：非阻塞入队（`queue.Queue`）；
  - 专属写线程消费队列，逐项执行（每个函数是 store 的写方法，如 `save_usage`/`save_event`），异常降级记日志不中断；
  - `flush(timeout)`：阻塞直到队列清空（测试/关停用）；`close()`：发哨兵停止线程并 join（lifespan 收尾）。
- [ ] FR2：`EventRecorder.record` / `UsageRecorder.record` 双模式：构造可选 `writer`——无 writer（默认）保持**同步直写**（现有测试与调用语义不变）；有 writer 则仅 `writer.submit(store.xxx, ...)` 入队返回（零阻塞）。`query/count/stats` 读路径不变（仍直读主连接）。
- [ ] FR3：`app.py` 组装单例 `SQLiteWriter(store)`，注入 `EventRecorder` 与 `UsageRecorder`；lifespan 收尾：`writer.flush()` + `writer.close()`（先于连接释放）。
- [ ] FR4：`/api/stats` 读路径零阻塞：handler 改 `await asyncio.to_thread(recorder.stats, ...)`；`UsageRecorder.stats` 加 **3 秒 TTL 缓存**（监控台 10s 轮询 → 命中缓存，事件循环零占用；`?hours` 变化作缓存 key 的一部分）。
- [ ] FR5：`/api/events`（query/count）与 `/api/logs/overview` 的同步查询改 `await asyncio.to_thread(...)`（移出事件循环；`LogsOverview` 内部聚合与 `recent_usage_rate` 一并由调用方 to_thread 包住）。
- [ ] FR6：`Forwarder` 出站客户端开启 `http2=True` 尝试（多路复用；上游不支持时 httpx 自动回退 HTTP/1.1，行为不变）。
- [ ] FR7：新增 `tests/test_writer.py`：submit 后未 flush 不可见 → flush 后可见；多任务顺序落库；异常任务降级不中断；close 后队列收尾（线程退出）。

### 3.2 非功能需求

- 性能：转发热路径（非流式响应构造前 / 流式 chunk 间）**零同步 SQLite**；轮询聚合对转发零影响。
- 可靠性：写队列积压时仅延迟落库不丢数据（进程正常退出前 lifespan flush；异常退出最多丢队列内未 flush 的条目——与原同步语义的差异仅在"崩溃瞬间"窗口，可接受并在 PRD 记录）；写失败降级不抛（同现有语义）。
- 兼容：无 writer 时行为与现状逐字节一致（默认参数）；HTTP 契约零变化。

## 4. 接口定义

- 新增内部类 `SQLiteWriter`（`submit/flush/close`，下划线包内使用）；recorder 构造新增可选参数 `writer`（默认为 None）。
- 对外 HTTP API 无变化。

## 5. 验收标准

- [ ] AC1：`pytest` 全绿（138 现有 + 新增 writer 用例）；`ruff check src tests` 0 告警。
- [ ] AC2：转发与轮询热路径 grep 确认无同步 sqlite 写调用：`usage.record`/`event.record` 在注入 writer 后仅 `submit`；`/api/stats` 命中缓存不执行聚合（缓存命中日志或时序断言）。
- [ ] AC3：端到端基准：直连 vs 优化后池子（独立实例、真实上游），多轮交替（≥3 批次 ×3 次），首 chunk **中位数差 ≤ 50ms**；流式 chunk 间隔 P90 与直连同量级（≤10ms）。
- [ ] AC4：`/api/events`、`/api/logs/overview`、`/api/stats` 在外加同步工作负载（模拟轮询）时仍即时响应（to_thread 生效，用测试断言 handler 完成时间无明显拖长）。
- [ ] AC5：生命周期：lifespan 收尾 flush 后事件/用量全部落库（关停测试）；运行中 48700 全程不受影响（独立实例验证，不杀 48700）。
- [ ] AC6：前端零改动回归 vitest/eslint/build 全绿；CI 三 job 全绿；三联动（PRD 已验收 + TODO G7 done + CHANGELOG）+ README 无 API 变更不需同步。

## 6. 测试计划

- 单元：`test_writer.py`（入队/flush/异常降级/close）；recorder 双模式（默认同步直写断言不变；注入 writer 后 submit 断言一次）。
- 集成：现有 `test_events_api`/`test_proxy`/`test_usage` 在不带 writer 下全绿（兼容路径）；新增一个带 writer 的端到端用例（请求后 flush → 事件可见）。
- 手动：独立端口起优化后实例，跑基准脚本（直连 vs 池子交替），记录并归档数据；`/api/stats` 重复请求命中缓存（响应时间 <5ms）。
- 回归：前端 vitest + eslint + build；运行中 48700 健康检查前后对比。

## 7. 里程碑与估算

| 子任务 | 预估 |
|---|---|
| store/writer.py + 单测 | 20 分钟 |
| recorder 双模式接入 + app.py 组装/收尾 | 25 分钟 |
| stats 缓存 + 三 API to_thread | 20 分钟 |
| http2 尝试 + 验证 | 10 分钟 |
| 端到端基准 + 全量验证 | 25 分钟 |
| 三联动 + CHANGELOG | 10 分钟 |

## 8. 风险与对策

| 风险 | 对策 |
|---|---|
| 写队列线程与主连接并发 | 写线程独占连接；读路径也经 to_thread（sqlite3 模块内部门锁），WAL 读写并行 |
| 测试时序：异步落库导致查询为空 | 无 writer 默认同步（现有测试零改动）；带 writer 用例显式 flush |
| 崩溃丢未 flush 数据 | lifespan flush 收尾；崩溃窗口极小且仅丢"最近几条事件"，统计/状态均以 DB 为准可自愈 |
| http2 上游不支持 | httpx 自动回退 http/1.1；基准结果不因回退变化（验证冒烟） |
| 缓存致监控台数据变旧 | TTL 3s << 轮询 10s，无感知 |
| 端到端基准受上游抖动干扰 | 多轮交替 + 中位数口径；直连与池子同批次交替，均摊抖动 |

## 9. 变更记录

| 日期 | 变更内容 | 理由 |
|---|---|---|
| 2026-08-21 | 初始定稿 | — |
| 2026-08-21 | 实现完成：FR6（http2 尝试）**放弃**——`http2=True` 需额外依赖 `httpx[http2]`（h2 包），对单请求/流式透传本地开销无实质收益（连接复用已解决主要瓶颈），不引入未声明依赖；其余 FR1-FR5/FR7 全部实现（SQLiteWriter 单写线程 / recorder 双模式 / stats 3s TTL 缓存 + 三 API to_thread / lifespan flush+close / test_writer 6 例） | 阶段 G7 开发 |