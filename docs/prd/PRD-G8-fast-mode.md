# PRD-G8-极致性能模式·成功请求快路径与资源上限

> 状态生命周期：草稿 → 评审 → approved（定稿）→ 开发中 → 已验收

## 元信息

| 字段 | 值 |
|---|---|
| 阶段 | G8 |
| 名称 | 极致性能模式 · 成功请求快路径与资源上限 |
| 状态 | 草稿 |
| 创建日期 | 2026-08-21 |
| 定稿日期 | 2026-08-21 |
| 验收日期 | 2026-08-21 |
| 关联文档 | docs/TODO.yaml 阶段 G8；apps/backend/src/opencode_pool/config.py；apps/backend/src/opencode_pool/metrics/fast.py（新建）；apps/backend/src/opencode_pool/store/writer.py；apps/backend/src/opencode_pool/usage/recorder.py；apps/backend/src/opencode_pool/events/recorder.py；apps/backend/src/opencode_pool/proxy/forwarder.py；apps/backend/src/opencode_pool/app.py |

## 1. 背景与目标

- **背景**：用户要求「几乎不占内存和 CPU 的超级方案、和直连保持一样的速度」。上一轮（G7）已把落库移出事件循环（单写线程队列），但 G7 不是"几乎零 CPU/内存"的最终方案——基线审计确认三点：
  1. `SQLiteWriter` 用无限队列（`queue.Queue()`）：积压时内存无限增长，是资源风险；
  2. `UsageRecorder.record` 每请求仍生成时间戳 / 参数元组 / 任务对象，写线程仍需逐条 `INSERT + commit`；
  3. `EventRecorder.record` 每成功请求仍构造完整事件 JSON（dict 组装 + `json.dumps` 两次 + writer 入队）——成功路径的逐条落地与"零 CPU/内存"互相冲突。
  结论：必须提供明确的 **FAST_MODE**，把成功请求从"逐条持久化"改为"固定上限内存聚合"。
- **目标**：新增 `FAST_MODE` 配置（默认关闭，行为与 G7 逐字节一致）；开启后成功请求只更新固定上限的内存聚合（无 dict/JSON 构造、无 SQLite 写入、无队列入队），失败/切换/冷却/禁用事件完整保留；`SQLiteWriter` 改有界队列（满载非阻塞、不无限增长）；`/api/stats` 保持现有字段契约并标注 FAST_MODE 数据口径。验收口径：FAST_MODE 下本地同 fake 上游控制实验，直连 vs 池子首 chunk **中位数差 ≤ 10ms**；进程内存/CPU 占用不再随请求量线性增长。
- **非目标**：不做成功逐条历史的持久化（FAST_MODE 下重启后成功聚合丢失，语义明确接受）；不改事件表结构与 `/api/events` HTTP 契约；不做聚合结果的磁盘落盘（崩溃恢复不保证）；不改监控台轮询频率与 UI 布局（仅加口径徽章）；不引入新依赖（标准库 `threading`/`collections.deque`/`queue`）；不改选号策略与转发逻辑。

## 2. 摸底结论（已执行）

- `forwarder.py` 成功路径（流式 `_on_stream_done` / 非流式 `_forward_once`）：`pool.record_success`（健康态零落库，保留）+ `usage.record(kind="success")` + `_emit_request(succeeded=True)`；失败路径 `usage.record(kind="error")` + `_emit_request(succeeded=False)` + 切换/失效状态事件。
- `UsageRecorder.record`：同步 `def`，G7 后注入 writer 时仅 `submit`；构造时间戳 + 8 参数元组仍在事件循环线程。
- `EventRecorder.record`：组装 `{"type","data","meta","time"}` + `_dumps(data)` + `_dumps(meta)`（两次 `json.dumps`），注入 writer 时 `submit(save_event, ...)`。
- `SQLiteWriter`：无限 `queue.Queue` + 单写线程逐条执行；无满载策略（`put` 阻塞但队列无限大因此永不阻塞——代价是内存无限增长）。
- `/api/stats`：G7 后 `await asyncio.to_thread(recorder.stats, ...)` + 3s TTL 缓存；数据源 = `store.aggregate_usage + store.events_summary`（均基于 DB）。
- **FAST_MODE 短路点设计**：`record` 入口短路（构造 event dict 之前）即可砍掉最重的 JSON 构造 + 入队/落库；forwarder 侧事件数据 dict 组装（微秒级、无序列化）保留，forwarder 保持统一调用路径零分支（少改少错，测试不破）。
- **stats 数据源切换**：FAST_MODE 下成功请求不进 DB（usage_events/events 均无），`aggregate_usage`/`events_summary` 的 duration/protocol 维度数据不全——必须由内存聚合（FastMetrics）生成 stats 主体；`summary.event_counts`（key_switch/cooldown/disabled 等状态事件）仍从 DB 取（状态事件落库，频度极低）。

## 3. 需求范围

### 3.1 功能需求

- [ ] FR1：`config.py` 新增 `fast_mode: bool = False`（环境变量 `FAST_MODE` 覆盖，pydantic-settings 大写自动映射）；`.env.example` 补充示例。
- [ ] FR2：新建 `metrics/fast.py`——`FastMetrics` 内存聚合器：
  - 按小时桶滚动窗口，最多 `FAST_WINDOW_HOURS = 168` 桶，超窗丢弃最旧桶（有界）；
  - 每桶聚合：totals（request_count / success_count / prompt_tokens / completion_tokens / duration 样本队列 ≤ `FAST_DURATION_SAMPLES = 500`（超出丢最旧）/ protocol Counter）/ per_account 计数 / per_account_models 计数（键 `(account_id, model)`，模型集受上游模型清单约束，实际有界）；
  - 全局 error_types Counter；
  - `update(...)` 单次 O(1)；`snapshot(hours)` 输出与 `aggregate_usage + events_summary(耗时/协议部分)` 兼容的结构；
  - 线程安全（`threading.Lock`；record 在事件循环线程、stats 在 `to_thread` 工作线程）。
- [ ] FR3：`store/writer.py` 有界化——`SQLiteWriter(maxsize=2000)` 改有界队列 + `droppable` 标记：
  - `submit(fn, *args, droppable=False)` 满载时**绝不阻塞**：新任务 droppable（可重建的成功快照）→ 直接丢弃并计数；新任务不可丢（失败/状态事件）→ 从队列中驱逐最旧一个 droppable 任务腾位（无 droppable 则丢弃新任务并计数）；
  - 暴露 `dropped` 计数（测试/日志）；
  - `flush()/close()` 语义保持（现有 test_writer 用例不破坏）。
- [ ] FR4：`UsageRecorder` 加 `fast_mode: bool = False` 构造参数：
  - 开启时 `record()` 仅调用 `FastMetrics.update(...)`（成功/失败都聚合，含 tokens/duration/protocol/error_type），**不构造事件参数、不 submit、不写 usage_events**；
  - `stats()` 开启时从 FastMetrics 生成（纯内存实时快照，跳过 3s TTL 缓存路径）；`summary` 的 `duration_ms`/`protocol` 来自 FastMetrics，`event_counts` 仍取 `store.events_summary()` 的状态事件计数（try/except 降级默认结构）；
  - 关闭时行为与 G7 逐字节一致。
- [ ] FR5：`EventRecorder` 加 `fast_mode: bool = False` 构造参数：
  - 开启时 `record(REQUEST, data)` 且 `data.get("success")` 为真 → 在构造 event dict **之前**短路返回（零 JSON 构造、零入队）；
  - 其余事件（失败 request / key_switch / cooldown / disabled / all_keys_* / gateway_key_*）完整保留（含 submit）；
  - 统一给 submit 传 `droppable = (type_ == REQUEST and data.get("success"))`（normal 模式下 writer 满载时也可驱逐成功快照）。
- [ ] FR6：`app.py` 组装：`_build_pool` 从 settings 读 `fast_mode`，注入 `UsageRecorder(store, writer=writer, fast_mode=...)` 与 `EventRecorder(store, writer=writer, fast_mode=...)`；`/api/stats` 响应新增 `mode: "fast" | "normal"` 字段（recorder.stats 输出，handler 零改动）；`forwarder` 零改动（短路发生在 recorder 层）。
- [ ] FR7：前端口径标注：`types/pool.ts` 的 StatsResponse 加 `mode?: "fast" | "normal"`；StatsSummaryCard 在 `mode === "fast"` 时显示口径徽章（文案：性能模式：成功请求仅内存聚合，重启后逐条历史不保留——i18n `stats.fastMode` key，zh/en）。

### 3.2 非功能需求

- 性能：FAST_MODE 下成功请求热路径 = 1 次锁保护的内存计数更新（O(1)，µs 级），零 IO、零 JSON、零入队；本地控制实验首 chunk 中位差 ≤ 10ms。
- 资源上限：内存聚合固定上限（≤ 168 桶 × (1 + 账号 + 账号×模型) 计数 + 168×500 duration 样本 ≈ 2MB 级）；writer 队列有界（默认 2000），满载不阻塞不增长。
- 可靠性：失败/切换/冷却/禁用事件在 FAST_MODE 下不丢；成功逐条历史在 FAST_MODE 下不保证（重启丢失，显式语义，UI/API 标注）；normal 模式行为与 G7 一致（仅满载极端场景下成功快照可被驱逐，取舍已记录）。
- 兼容：`/api/stats` 字段契约保持（新字段 `mode` 为可选扩展，旧前端容错）；`/api/events` 契约零变化；配置默认 `fast_mode=false` 不影响现有部署。

## 4. 接口定义

- 配置：`FAST_MODE`（bool，默认 false，`.env`/环境变量）。
- 内部类：`FastMetrics`（`update/snapshot`）；`SQLiteWriter` 构造新增 `maxsize`，`submit` 新增关键字 `droppable`，新增只读 `dropped`。
- `/api/stats` 响应新增可选字段 `mode: "fast" | "normal"`（其余字段不变）。
- 对外 HTTP API 其余部分无变化。

## 5. 验收标准

- [ ] AC1：FAST_MODE 单测——成功 `usage.record` 后 `usage_events` 无新记录、FastMetrics 计数 +1；成功 `event.record(REQUEST, success=True)` 后 `events` 无新记录（短路发生在事件构造前，用单元断言验证）。
- [ ] AC2：FAST_MODE 下单测——失败 `usage.record` / 失败 request 事件 / key_switch / cooldown / disabled / all_keys_* 事件全部保留并落库可见。
- [ ] AC3：writer 有界单测——maxsize=2 灌满后 `submit` 不阻塞立即返回；droppable 满载被丢弃且 `dropped` 计数正确；不可丢任务满载入队时驱逐最旧 droppable 且自身落库；全部不可丢时丢弃新任务不抛；`flush/close` 语义不变（现有 test_writer 6 例不破坏）。
- [ ] AC4：`stats` 契约——FAST_MODE 下 `stats(hours)` 结构与 normal 一致（totals/success_rate/per_account/per_account_models/buckets/error_types/summary 全字段 present）+ `mode: "fast"`；normal 模式输出与 G7 完全一致；`pytest` 全绿 + `ruff check src tests` 0。
- [ ] AC5：端到端基准——独立实例开 FAST_MODE，直连 vs 池子→同一 fake 上游多轮交替，首 chunk **中位数差 ≤ 10ms**；真实上游同账号控制实验只报告网络差异（多轮交替中位数）。
- [ ] AC6：前端——vitest / eslint / build 全绿；`mode === "fast"` 时口径徽章显示；运行中 48700 全程不受影响（独立实例验证，不杀 48700）。
- [ ] AC7：CI 三 job 全绿；三联动收尾（PRD 已验收 + TODO G8 done + CHANGELOG 追加）；`.env.example` 与 README（FAST_MODE 数据语义说明）同步。

## 6. 测试计划

- 单元：`tests/test_fast_metrics.py`（window 滚动裁剪 / duration 样本上限 / protocol 与 error_types 聚合 / per_account_models 归组 / snapshot 结构）；`test_writer.py` 扩展有界与驱逐用例；`test_usage.py`/`test_events.py` 扩展 fast 模式短路与保留用例。
- 集成：现有全量 pytest（144+）在默认模式（fast_mode=False）下零改动全绿；新增 fast 模式端到端用例（fast recorder + flush 后 events 仅含状态事件）。
- 手动：独立端口起 FAST_MODE 实例跑基准脚本（直连 vs 池子交替，中位数口径记录归档）；`/api/stats` 在 FAST_MODE 下返回 `mode: "fast"` 且耗时 <5ms。
- 回归：前端 vitest/eslint/build；运行中 48700 健康检查前后对比；真实上游多轮交替只报告差异。

## 7. 里程碑与估算

| 子任务 | 预估 |
|---|---|
| 摸底验证 + PRD 定稿 | 已完成 |
| metrics/fast.py + 单测 | 25 分钟 |
| writer 有界化 + 驱逐策略 + 单测 | 25 分钟 |
| recorder fast_mode + app 组装 + mode 字段 | 25 分钟 |
| 前端类型 + 口径徽章 | 15 分钟 |
| 端到端基准 + 全量验证 | 30 分钟 |
| 三联动 + CHANGELOG + README | 10 分钟 |

## 8. 风险与对策

| 风险 | 对策 |
|---|---|
| FAST_MODE 重启丢成功聚合数据 | 明确语义（成功逐条历史不保证）；失败/状态事件在 DB 保留可追溯；UI 徽章 + README 说明口径 |
| stats 在 FAST_MODE 与 DB 历史不一致 | 只保证 FAST_MODE 会话内连续性；API 标注 `mode` 字段，前端徽章明示口径 |
| writer 驱逐逻辑线程安全问题 | deque + Lock 自实现，单测覆盖满载/驱逐/计数场景；写线程仍唯一消费 |
| duration p95 采样偏差 | 每桶固定样本窗口（≤500），超出丢最旧；p95 为近似值（与 E4 `events_summary` 同口径思路） |
| forwarder 侧成功路径仍组装事件 dict | 仅微秒级无序列化开销；短路在 recorder 层（构造 JSON 之前）已砍掉最重成本；forwarder 保持零分支零改动 |
| 默认模式行为变化（满载驱逐成功快照） | 触发条件为极端积压（写线程落后），此时保转发流畅优先；掉落仅影响成功逐条历史，统计/状态自愈 |

## 9. 变更记录

> **本小节是需求变更的审计轨迹（强制）**：任何对正文 FR / AC / 技术方案的修改，
> MUST 在此追加一行（日期 + 变更内容 + 理由），并重核受影响 AC（结果留痕）。

| 日期 | 变更内容 | 理由 |
|---|---|---|
| 2026-08-21 | 初始定稿 | — |
| 2026-08-21 | 实现完成：FR1-FR7 全部落地——config.fast_mode（FAST_MODE 环境变量）；metrics/fast.py FastMetrics（168 小时桶窗口 + 每桶 500 耗时样本上限 + per_account/per_account_models/error_types/protocol 聚合，snapshot 与 aggregate_usage 契约兼容）；SQLiteWriter 有界化（maxsize=2000，满载非阻塞：droppable 直接丢弃、不可丢任务驱逐最旧 droppable，dropped 计数，驱逐同步递减 pending 防 flush 死锁）；UsageRecorder/EventRecorder fast_mode 短路（成功 request 不构造事件 JSON 不落库，失败/状态事件保留，usage submit 标 droppable=kind==success）；forwarder 4 处 record 补 duration_ms/protocol（仅 fast 聚合使用，save_usage 无这两列）；/api/stats 输出 mode 字段（fast/normal）；前端 StatsResponse.mode + FAST 徽章（i18n stats.fastMode）；.env.example 说明；测试新增 test_fast_metrics 8 例 + test_fast_mode 7 例 + test_writer 有界 2 例（共 25 例，全量 pytest 163 绿 + ruff 0） | 阶段 G8 开发 |