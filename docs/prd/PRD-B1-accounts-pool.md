# PRD-B1-账号池配置与状态机

> 状态生命周期：草稿 → 评审 → approved（定稿）→ 开发中 → 已验收

## 元信息

| 字段 | 值 |
|---|---|
| 阶段 | B1 |
| 名称 | 账号池配置与状态机 |
| 状态 | approved |
| 创建日期 | 2026-08-19 |
| 定稿日期 | 2026-08-19 |
| 验收日期 | — |
| 关联文档 | docs/TODO.yaml 阶段 B1 |

## 1. 背景与目标

- **背景**：多 OpenCode Go 订阅账号需要一个统一的账号池：集中配置、运行时状态追踪、健康度管理。B1 先实现账号池的**配置加载与状态机**，不做实际代理转发（B2）与自动切换（B3）。
- **目标**：后端能加载多账号配置（密钥引用环境变量），维护每个账号的运行状态（healthy / cooldown / disabled），并提供账号状态查询 API 供前端大盘使用。
- **非目标**：不实现 Responses 转发（B2）；不实现额度错误识别与自动切换（B3）；不做状态持久化（B4，本阶段内存态即可）；不接前端 UI（C 阶段）。

## 2. 需求范围

### 2.1 功能需求

- [ ] FR1：账号配置来源：`config/accounts.yaml` + 环境变量引用（`api_key: ${OPENCODE_GO_KEY_1}` 形式），支持多账号。
- [ ] FR2：账号数据结构：`account_id` / `name` / `api_key`（解析后的真实密钥，运行时持有，不落日志）/ `models`（可选，空 = 全部）/ `enabled`（可选，默认 true）。
- [ ] FR3：账号状态机：每个账号有 `status` ∈ {`healthy`, `cooldown`, `disabled`}`，附状态字段：`cooldown_until`（datetime 或 None）、`last_error`（str 或 None）、`error_count`（int）。
- [ ] FR4：状态流转：
  - `marked_down(reason)`：healthy → cooldown，设置 cooldown_until = now + TTL，error_count+1；
  - `clear()`：任意状态 → healthy，清空 cooldown_until / last_error / error_count；
  - `disable(reason)` / `enable()`：手动禁用/启用（disabled 优先于其他状态）；
  - `cooldown_expired()`：cooldown 到期后调用自动恢复 healthy（TTL 默认 5 小时 = 18000s，可配置）。
- [ ] FR5：`AccountPool` 对外提供：`get_all()`（含脱敏视图）、`pick_next()`（当前阶段返回第一个 healthy 的账号；B3 再接路由策略）、`mark_down(account_id, reason)`、`clear_account(account_id)`、`account(id)`。
- [ ] FR6：查询 API：`GET /api/accounts` 返回账号池脱敏视图（不暴露 api_key，只含 `id` / `name` / `status` / `cooldown_until` / `last_error` / `error_count` / `enabled`）。
- [ ] FR7：密钥脱敏：日志与 API 输出中 api_key 一律打码（`sk-****abcd` 形式，仅显示末 4 位）。

### 2.2 非功能需求

- 安全：api_key 不落日志、不进 API 响应；未配置任何环境变量引用的账号加载时报清晰错误。
- 可测试：状态机纯逻辑可单测（不依赖真实网络/时钟，时钟可注入）。
- 兼容性：配置加载同时支持 YAML（PyYAML）与 JSON；缺失 `config/accounts.yaml` 时返回空池但可启动。

## 3. 技术方案

- 目录新增：

```
apps/backend/src/opencode_pool/
├─ config/accounts.example.yaml    # 配置样例（占位符，不落真实密钥）
├─ accounts/
│  ├─ __init__.py                  # 导出 AccountPool、AccountStatus
│  ├─ models.py                    # Account 数据类 + AccountStatus 枚举 + 状态字段
│  ├─ pool.py                      # AccountPool：加载 + 状态机 + 脱敏视图
│  └─ loader.py                    # 从 YAML/JSON + 环境变量解析成 Account 列表
└─ api/accounts.py                 # FastAPI router：GET /api/accounts
```

- 时钟注入：`AccountPool(now: Callable[[], datetime] = datetime.now)`，测试用固定时钟。
- 依赖：新增 `PyYAML`（开发依赖已有 `pytest/httpx`，`PyYAML` 加进 runtime deps）。
- 状态机常量：

```python
class AccountStatus(enum.StrEnum):
    HEALTHY = "healthy"
    COOLDOWN = "cooldown"
    DISABLED = "disabled"
```

## 4. 接口定义

- 配置样例 `config/accounts.example.yaml`：

```yaml
accounts:
  - id: opencode-go-1
    name: OpenCode Go 主账号
    api_key: ${OPENCODE_GO_KEY_1}
  - id: opencode-go-2
    name: OpenCode Go 备用账号
    api_key: ${OPENCODE_GO_KEY_2}
    enabled: false
```

- `GET /api/accounts` → 200：

```json
{
  "accounts": [
    {"id": "opencode-go-1", "name": "OpenCode Go 主账号", "status": "healthy",
     "cooldown_until": null, "last_error": null, "error_count": 0, "enabled": true}
  ]
}
```

- 状态机 API（内存态，B4 持久化）：

```python
pool.mark_down("opencode-go-1", "quota exhausted")   # healthy -> cooldown (TTL 18000s)
pool.clear_account("opencode-go-1")                   # -> healthy
pool.disable("opencode-go-1", "manual")               # -> disabled
pool.enable("opencode-go-1")                          # -> healthy（若在 cooldown -> cooldown 等剩余过期）
pool.pick_next() -> Account | None                    # 首个 healthy 且 enabled 的账号
```

## 5. 验收标准

- [ ] AC1：`cd apps/backend && pytest` 全绿（新增 test_accounts.py 覆盖加载/状态机/脱敏）。
- [ ] AC2：`ruff check src tests` 无警告。
- [ ] AC3：加载 `accounts.example.yaml`（env 有对应密钥）能生成多账号池；缺失密钥变量时报清晰错误。
- [ ] AC4：`mark_down` 后 `pick_next` 跳过该账号；TTL 到期后 `pick_next` 恢复可用；`disable` 后 `pick_next` 跳过。
- [ ] AC5：`GET /api/accounts` 返回脱敏视图，不含 api_key 字段；日志无明文密钥。
- [ ] AC6：未配置 `config/accounts.yaml` 时应用可启动且 `/api/accounts` 返回空列表。

## 6. 测试计划

- 单元：状态机流转（mark_down/clear/disable/enable/cooldown 到期）用注入时钟断言；
- 单元：loader 解析 YAML + env 引用 + 缺失变量报错；
- 单元：脱敏函数（无 key / 短 key / 正常 key）；
- 集成：TestClient 打 `/api/accounts`，断言响应结构与脱敏。

## 7. 里程碑与估算

| 子任务 | 预估 |
|---|---|
| models + loader | 20 分钟 |
| pool 状态机 | 30 分钟 |
| API + 脱敏 | 15 分钟 |
| 测试 + lint | 25 分钟 |

## 8. 风险与对策

| 风险 | 对策 |
|---|---|
| 环境变量缺失导致加载失败 | loader 跳过该账号并记录明确警告，不崩整个服务 |
| 时钟依赖导致测试不稳定 | 注入 now 回调 |
| 状态机竞态（多协程 mark_down） | 单挑程内加锁（threading.Lock）；B4 持久化时再评估 |

## 9. 变更记录

| 日期 | 变更内容 | 理由 |
|---|---|---|
| 2026-08-19 | 初始定稿 | — |
