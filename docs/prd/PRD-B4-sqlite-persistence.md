# PRD-B4-状态持久化SQLite

> 状态生命周期：草稿 → 评审 → approved（定稿）→ 开发中 → 已验收

## 元信息

| 字段 | 值 |
|---|---|
| 阶段 | B4 |
| 名称 | 状态持久化（SQLite） |
| 状态 | 已验收 |
| 创建日期 | 2026-08-19 |
| 定稿日期 | 2026-08-19 |
| 验收日期 | 2026-08-19 |
| 关联文档 | docs/TODO.yaml 阶段 B4；docs/prd/PRD-B1/B2/B3 |

## 1. 背景与目标

- **背景**：B1-B3 的账号池状态（status / cooldown_until / consecutive_failures / enabled / 切换历史）全是进程内内存态，服务重启全部丢失——一个账号刚被 429 冷却 5 小时，重启后又变 healthy 继续被调用，违背"多账号窗口跟踪"的初衷。
- **目标**：账号池的运行时状态与切换历史持久化到 SQLite，服务重启后自动恢复，不丢冷却/禁用/统计信息。
- **非目标**：不做账号密钥持久化（api_key 仍只从配置 + 环境变量读，DB 不存密钥）；不做分布式一致性（单实例单文件）；不做前端展示（C 阶段）；不做数据库选型扩展（固定 SQLite，Python 内置 sqlite3）。

## 2. 需求范围

### 2.1 功能需求

- [ ] FR1：SQLite 存储层 `AccountStore`：建表、读写账号运行时状态（id / status / cooldown_until / last_error / error_count / consecutive_failures / enabled）与切换历史（ts / account_id / kind / reason）。
- [ ] FR2：DB 路径可配置：`settings.db_path`（默认 `data/opencode_pool.db`），目录不存在自动创建；`.gitignore` 已排除 `data/` 与 `*.db`。
- [ ] FR3：启动加载：`create_app` 构建账号池后，从 DB 恢复每个账号的运行时状态（覆盖配置默认的 healthy）；DB 中无记录则保持配置初始状态。
- [ ] FR4：状态保存时机：每次账号状态变更（mark_down / clear_account / disable / enable / record_success / scan_cooldowns 恢复）后增量写回 DB（同事务，锁内）。
- [ ] FR5：切换历史持久化：`_record_event` 同步写 DB（追加 + 按容量裁剪保留最近 N=100）；`switch_history()` 优先从内存读（与 DB 一致），DB 为持久备份。
- [ ] FR6：重启恢复正确性：cooldown 中但已到期的账号恢复后应转为 healthy（恢复逻辑基于当前时间，不依赖 DB 存储的时间）；enabled=false 保持禁用。
- [ ] FR7：无 DB 文件/目录写入失败时的降级：DB 不可写时记录警告并退化为纯内存（不崩服务；C 层可提示持久化未生效）。

### 2.2 非功能需求

- 性能：状态写低频（每次状态变更一次），SQLite 单写者足够；启动恢复一次全量读。
- 健壮性：DB 损坏/表不存在时重建；写失败不污染内存态。
- 可测：DB 用 `:memory:` 或用 tmp_path 临时文件；测试隔离不落真库。
- 兼容性：不改变 `AccountPool` 对外 API（持久化是内部增强）。

## 3. 技术方案

- 新增文件：

```
apps/backend/src/opencode_pool/
├─ store/
│  ├─ __init__.py          # 导出 AccountStore
│  └─ sqlite_store.py      # AccountStore：连接管理 + 表结构 + load/save/write_event
```

- `AccountPool` 接入：新增可选 `store: AccountStore | None` 构造参数；内部所有状态变更点调用 `self._persist(a)`（把账号一行写回 DB）。

- 表结构：

```sql
CREATE TABLE IF NOT EXISTS accounts (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    cooldown_until TEXT,             -- ISO 或 NULL
    last_error TEXT,
    error_count INTEGER NOT NULL DEFAULT 0,
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    enabled INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS switch_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    account_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    reason TEXT
);
```

- 裁剪：写历史时 `DELETE FROM switch_history WHERE id NOT IN (SELECT id FROM switch_history ORDER BY id DESC LIMIT 100)`。

- 恢复逻辑（升级版本 `_maybe_recover` 同源）：加载后若 status=cooldown 且 cooldown_until 已过期 → 置 healthy（用当前时间）。

## 4. 接口定义

- `AccountStore(db_path: str)`：
  - `connect()`：打开连接、建表、WAL 模式。
  - `load_accounts_state() -> dict[str, dict]`：返回 id → 状态字典。
  - `save_state(account: Account)`：写一行（UPSERT）。
  - `write_event(ts, account_id, kind, reason)`：追加历史 + 裁剪。
  - `close()`。
- `AccountPool(..., store: AccountStore | None = None)`：增 optional 参数。
- `create_app`：`store = AccountStore(settings.db_path)`；`pool = AccountPool(accounts, store=store)`；`pool.restore_from_store()` 在构建后调用。

## 5. 验收标准

- [ ] AC1：`pytest` 全绿（新增 test_sqlite_store.py + test_persistence.py）。
- [ ] AC2：`ruff check src tests` 无警告。
- [ ] AC3：`AccountStore` 对 `:memory:` DB 能 save/load 账号状态，字段保真（status/cooldown/consecutive/enabled）。
- [ ] AC4：模拟重启：pool A（store 同文件）mark_down 一个账号 → close；新建 pool B（同一 db）→ restore 后该账号仍 cooldown（未到期），consecutive_failures 保留。
- [ ] AC5：cooldown 到期后重启恢复为 healthy（用注入时钟验证：mark_down 短 TTL → 推进时钟 → 新 pool 加载后 healthy）。
- [ ] AC6：禁用账号（enabled=false）重启后仍禁用（不参与 pick）。
- [ ] AC7：切换历史写入 DB，重启后 `switch_history()` 与恢复前一致（最近 N 条）。
- [ ] AC8：DB 不可写（如只读路径）时应用可启动且日志有警告，服务不崩。
- [ ] AC9：`db_path` 可经 env `DB_PATH` 配置，默认 `data/opencode_pool.db`；数据目录自动创建。

## 6. 测试计划

- 单测 store：内存 DB 的 save/load/write_event/裁剪。
- 单测 pool 持久化：注入 tmp store，mark_down/clear/enable/scan 后断言 DB 一致。
- 集成：两个先后 `create_app` 用同一 db 文件 → 验证状态跨实例恢复（模拟重启）。
- 降级：store 构造指向只读路径 → 断言应用可启动 + 有警告。

## 7. 里程碑与估算

| 子任务 | 预估 |
|---|---|
| sqlite_store.py（连接/建表/读写/裁剪） | 30 分钟 |
| AccountPool 接入持久化 | 30 分钟 |
| create_app 接线 + 配置 | 15 分钟 |
| 测试（store + 重启恢复 + 降级） | 40 分钟 |

## 8. 风险与对策

| 风险 | 对策 |
|---|---|
| 每次改状态都写 DB 性能 | 状态变更低频（窗口级）；WAL 模式 + 原子 UPSERT |
| 时序：cooldown 写入时间 vs 到期 | 恢复时用当前时间判断，不信任 DB 存的"已恢复"标记 |
| 测试污染真实 DB | 测试全部用 :memory: 或 tmp_path，绝不触 data/ |
| store 写失败 | 捕获异常记 warning，退化内存态，不崩服务 |

## 9. 变更记录

| 日期 | 变更内容 | 理由 |
|---|---|---|
| 2026-08-19 | 初始定稿 | — |
| 2026-08-19 | 验收通过：pytest 61 passed（含 B4 新增 11 个）、ruff 无警告；SQLite 读写/重启恢复/到期恢复/禁用保持/DB 降级全覆盖，端到端实测重启冷却保留 | 阶段 B4 完成 |
