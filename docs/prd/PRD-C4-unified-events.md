# PRD-C4-统一事件日志

> 状态生命周期：草稿 → 评审 → approved（定稿）→ 开发中 → 已验收

## 元信息

| 字段 | 值 |
|---|---|
| 阶段 | C4 |
| 名称 | 统一事件日志 |
| 状态 | 已验收 |
| 创建日期 | 2026-08-20 |
| 定稿日期 | 2026-08-20 |
| 验收日期 | 2026-08-20 |
| 关联文档 | docs/TODO.yaml 阶段 C4；PRD-B1/B2/B3/B4/C2/C3 |

## 1. 目标与边界

当前 `switch_history` 只记录零散状态字段，无法回答一次请求是否成功、尝试过哪些账号、何时发生切换、为什么全部账号失效等问题。本阶段用一个统一事件模型替换旧日志结构。

不做 OpenCode 额度查询、不记录 API key 明文、不把上游错误正文未经脱敏写入事件。

## 2. 统一事件契约

所有事件必须是：

```json
{
  "type": "request",
  "data": {},
  "meta": {},
  "time": "2026-08-20T12:00:00+00:00"
}
```

- `type`：机器可筛选的事件类型；
- `data`：事件业务内容；
- `meta`：来源、request_id、协议、路由、schema_version 等公共上下文；
- `time`：事件发生时间，UTC ISO-8601。

### 2.1 事件类型

| type | 触发时机 | data 必备内容 |
|---|---|---|
| `request` | 每个入站转发请求结束 | request_id、success、protocol、model、stream、status_code、duration_ms、account_id、attempt_count、attempts、token、error |
| `key_cooldown_started` | key 因上游错误进入冷却 | account_id、reason、error_type、cooldown_until、cooldown_seconds、consecutive_failures |
| `key_cooldown_completed` | 冷却到期恢复健康 | account_id、previous_status、reason |
| `key_switch` | 当前 key 失败后实际选到另一个 key | from_account_id、to_account_id、reason、error_type、attempt、request_id |
| `all_keys_invalid` | 所有候选 key 均为 quota/auth 失败 | attempted_account_ids、error_types、request_id、attempt_count |
| `all_keys_unavailable` | 无健康 key或全部网络/服务失败 | attempted_account_ids、error_types、request_id、attempt_count |
| `key_disabled` | 自动/手动禁用 | account_id、reason、automatic |
| `key_enabled` | 启用 key | account_id、reason |
| `key_cooldown_cleared` | 手动清除冷却 | account_id、previous_status、reason |
| `gateway_key_created` | 生成网关访问 key | key_id、label（不含明文/hash） |
| `gateway_key_revoked` | 吊销网关访问 key | key_id、label |

## 3. 存储与迁移

新增 SQLite `events` 表：

```sql
CREATE TABLE events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  type TEXT NOT NULL,
  event_time TEXT NOT NULL,
  data_json TEXT NOT NULL,
  meta_json TEXT NOT NULL
);
```

- 按 `id DESC` 查询；保留最近 5000 条；
- 应用启动时检测旧 `switch_history`，逐行迁移为统一事件，然后 `DROP TABLE switch_history`；
- `usage_events` 是统计投影，不再作为事件日志来源；
- 所有 JSON 解码失败/数据库不可用都降级为空，不影响转发主路径。

## 4. API

- `GET /api/events?limit=100&type=request,key_switch`：返回 `{"events": [...]}`，每项严格含 `type/data/meta/time`；
- 删除 `/api/switch-history` 旧日志接口，前端统一消费 `/api/events`；
- `/api/stats` 继续读取 `usage_events` 聚合，不改变统计接口。

## 5. 验收标准

- [ ] AC1：统一事件单元测试覆盖契约校验、脱敏、类型筛选、限制条数。
- [ ] AC2：旧 SQLite 的 `switch_history` 可迁移到 `events`，迁移后旧表不存在，事件结构完整。
- [ ] AC3：fake upstream 成功、400、429→切换、全 quota/auth 失败、全网络失败分别生成 request、cooldown、switch、all-keys 事件。
- [ ] AC4：冷却恢复、手动清除/启用/禁用、网关 key 创建/吊销均产生统一事件。
- [ ] AC5：每个 request 事件含 request_id、成功结果、耗时、协议、模型、尝试链，且不含明文 key。
- [ ] AC6：`GET /api/events` 返回严格统一结构；前端时间线不再使用 `switch_history` 字段。
- [ ] AC7：后端 pytest/ruff、前端 vitest/lint/build 全部通过。

## 6. 变更记录

| 日期 | 变更内容 | 理由 |
|---|---|---|
| 2026-08-20 | 初始定稿：统一 type/data/meta/time 事件契约，替换 switch_history，保留 usage_events 作为统计投影 | 解决旧日志无法描述请求结果、账号切换和全账号失效的问题 |
