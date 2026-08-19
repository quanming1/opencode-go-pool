# PRD-B3-额度错误识别与自动切换强化

> 状态生命周期：草稿 → 评审 → approved（定稿）→ 开发中 → 已验收

## 元信息

| 字段 | 值 |
|---|---|
| 阶段 | B3 |
| 名称 | 额度错误识别与自动切换强化 |
| 状态 | approved |
| 创建日期 | 2026-08-19 |
| 定稿日期 | 2026-08-19 |
| 验收日期 | — |
| 关联文档 | docs/TODO.yaml 阶段 B3；docs/prd/PRD-B2-transparent-proxy.md |

## 1. 背景与目标

- **背景**：B2 已实现失败切换（错分类 + mark_down + 重试下一个），但账号恢复机制是"pick 时惰性检查冷却到期"，缺少主动恢复；连续失败没有阈值（坏账号会被反复尝试）；上游 429 常带 `Retry-After` 头但当前忽略（一律用固定 5h TTL）。B3 强化这三块，让切换更可靠、恢复更及时。
- **目标**：账号池具备主动冷却恢复、连续失败自动禁用、Retry-After 动态冷却；切换行为可观测（记录切换历史）。
- **非目标**：不做持久化（B4）；不做前端展示（C 阶段）；不做多账号权重/负载均衡路由（本轮延后，pick 仍取首个 healthy）；不做真实的 OpenCode 账号额度轮询接口探测（以错误信号为准）。

## 2. 需求范围

### 2.1 功能需求

- [ ] FR1：主动冷却恢复扫描：新增后台任务周期性（默认每 60s）扫描 `cooldown` 且已到期的账号并恢复 `healthy`，不再依赖"下一次 pick 才恢复"。
- [ ] FR2：Retry-After 支持：`mark_down(account_id, reason, retry_after=None)` 接受可选的 `retry_after` 秒（来自上游 `Retry-After` 响应头，解析优先于固定 TTL），设置 `cooldown_until = now + retry_after`。
- [ ] FR3：连续失败阈值自动禁用：`mark_down` 时若连续失败次数 ≥ `max_consecutive_failures`（默认 3）→ 账号进入 `disabled`（机器判定需人工确认，`last_error` 标记 "auto-disabled: consecutive failures"）；`clear_account` 成功时重置连续失败计数。
- [ ] FR4：连续失败语义：`error_count` 升级为"连续失败次数 + 总失败次数"（新增 `consecutive_failures` 字段；`error_count` 保留为累计）。`pick_next` 选中某账号时在内部记录该账号仍健康（连续失败清零由 `clear_account` 或成功使用触发）。
- [ ] FR5：切换历史：`AccountPool` 维护环形日志 `switch_history`（最近 N=20 条），记录每次 mark_down/切换事件（时间 / account_id / kind / reason），提供 `switch_history()` 查询；内容同时进日志。
- [ ] FR6：`GET /api/accounts` 脱敏视图扩展：新增 `consecutive_failures` 与 `cooldown_seconds_remaining`（若在冷却则剩余秒数，否则 null）。
- [ ] FR7：配置：`pool_scan_interval_seconds`（默认 60）、`max_consecutive_failures`（默认 3）进 Settings / .env.example；`AccountPool` 构造参数同步暴露。

### 2.2 非功能需求

- 性能：扫描任务轻量（O(账号数)），扫描间隔可配；不阻塞请求路径。
- 健壮性：后台任务异常被捕获并记录，不崩服务；关闭时优雅停止。
- 可测：后台扫描用时钟注入 + 手动触发 `scan_cooldowns()` 单测；不依赖真实时间。
- 兼容性：B2 的 `forward()` 调用 `pick_next()` / `mark_down(account_id, reason)` 签名保持向后兼容（新增参数有默认值）。

## 3. 技术方案

- 扩展 `Account`（models.py）：新增 `consecutive_failures: int = 0` 字段；`public_view()` 增加 `consecutive_failures`、`cooldown_seconds_remaining`。
- 扩展 `AccountPool`（pool.py）：

```python
def mark_down(self, account_id, reason, retry_after: int | None = None, kind: str = "error") -> bool
    # 设置 cooldown_until: now + (retry_after if retry_after else self._cooldown_seconds)
    # consecutive_failures += 1
    # if consecutive_failures >= max_consecutive_failures: -> disabled (auto)
    # append 到 switch_history

def scan_cooldowns(self) -> int:
    # 主动扫描：cooldown 且到期 -> healthy，返回恢复数

def record_success(self, account_id) -> None
    # 成功使用：consecutive_failures = 0（error_count 累计保留）

def switch_history(self, limit: int = 20) -> list[dict]
```

- `pick_next()` 改造：选中账号时调用 `record_success`（B2 语义延续——每次请求成功消耗一个账号视为成功）；内部先 `_maybe_recover` 再选。
- 后台任务：`apps/backend/src/opencode_pool/scheduler.py`——`async def run_pool_scanner(pool, interval, now?, stop_event)` 循环 `await asyncio.sleep(interval)` + `scan_cooldowns()`；`create_app` 启动时 `lifespan` 里 `asyncio.create_task` 并 `finally cancel`。
  - 为可测试：扫描器接受 `runner: callable` 或直接暴露 `scan_cooldowns()` 由测试手动调用；后台循环本身仅作集成验证。
- `Forwarder` 透传 `Retry-After`：上游响应头读取 `retry_after` → 传给 `mark_down(..., retry_after=n, kind=exc.kind.value)`。
- `switch_history` 数据：`{"ts": iso, "account_id": str, "kind": str, "reason": str}`。

## 4. 接口定义

- `mark_down` 扩展签名（向后兼容）：

```python
mark_down(account_id, reason, retry_after: int | None = None, kind: str = "error") -> bool
```

- `GET /api/accounts` 单条新增字段：

```json
{
  "id": "opencode-go-1",
  "name": "...",
  "status": "cooldown",
  "cooldown_until": "...",
  "cooldown_seconds_remaining": 123,
  "last_error": "quota: ...",
  "error_count": 4,
  "consecutive_failures": 3,
  "enabled": true
}
```

- 环境变量（.env.example）：`POOL_SCAN_INTERVAL_SECONDS=60`、`MAX_CONSECUTIVE_FAILURES=3`。

## 5. 验收标准

- [ ] AC1：`pytest` 全绿（新增 test_rotation.py 覆盖自动恢复/阈值禁用/Retry-After/切换历史）。
- [ ] AC2：`ruff check src tests` 无警告。
- [ ] AC3：调用 `scan_cooldowns()` 把已到期 cooldown 账号恢复 healthy，未到期不受影响。
- [ ] AC4：`mark_down(reason, retry_after=30)` → `cooldown_until` 在 now+30s；无 retry_after → 默认 TTL。
- [ ] AC5：连续失败达阈值 → status=disabled 且 last_error 含 "auto-disabled"；再 `record_success`/`clear_account` 后恢复 healthy 且连续失败归零。
- [ ] AC6：`GET /api/accounts` 返回含 `consecutive_failures` 与 `cooldown_seconds_remaining`。
- [ ] AC7：`switch_history()` 返回最近事件（含 mark_down 的 kind/reason）。
- [ ] AC8：Forwarder 遇到带 `Retry-After: 30` 的 429 时，账号冷却为 now+30s（而非 5h）。
- [ ] AC9：`scan_interval` / `max_failures` 可经 Settings 覆盖；默认分别为 60 / 3。

## 6. 测试计划

- 单测 pool：scan_cooldowns 恢复、mark_down retry_after、阈值自动禁用、record_success 清零、switch_history 环形。
- 集成：TestClient /api/accounts 字段；Forwarder 传 retry_after（MockTransport 构造 `Retry-After` 头）。
- 后台扫描器：手动调 `scan_cooldowns()` 断言；循环本身冒烟（短 interval + stop_event）。

## 7. 里程碑与估算

| 子任务 | 预估 |
|---|---|
| Account/AccountPool 扩展（字段 + 扫描 + 历史） | 40 分钟 |
| scheduler + app lifespan | 20 分钟 |
| Forwarder Retry-After 透传 | 15 分钟 |
| 测试 + lint | 40 分钟 |

## 8. 风险与对策

| 风险 | 对策 |
|---|---|
| 后台任务在测试/单实例下干扰 | lifespan 启动 + stop_event 清晰停止；扫描纯逻辑可单测 |
| scan_interval 太短频繁扫 | 默认 60s 可配；扫描 O(n) 轻量 |
| record_success 触发点不准 | 在 Forwarder 成功转发后调用（2xx 时）而非 pick 时，更贴合"成功使用"语义 |
| 阈值误禁用健康账号 | 默认 3 次连续失败才禁用；人工 enable 可恢复 |

## 9. 变更记录

| 日期 | 变更内容 | 理由 |
|---|---|---|
| 2026-08-19 | 初始定稿 | — |
