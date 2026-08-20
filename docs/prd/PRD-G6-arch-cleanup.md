# PRD-G6-优化架构·后端 API 层结构性冗余收敛

> 状态生命周期：草稿 → 评审 → approved（定稿）→ 开发中 → 已验收

## 元信息

| 字段 | 值 |
|---|---|
| 阶段 | G6 |
| 名称 | 优化架构 · 后端 API 层结构性冗余收敛 |
| 状态 | approved |
| 创建日期 | 2026-08-21 |
| 定稿日期 | 2026-08-21 |
| 验收日期 | — |
| 关联文档 | docs/TODO.yaml 阶段 G6；apps/backend/src/opencode_pool/proxy/router.py；apps/backend/src/opencode_pool/api/ |

## 1. 背景与目标

- **背景**：后端 API 层在 C3（网关鉴权）与 C4（统一事件）演进中累积了**三处结构性冗余**——它们不是死代码，而是「结构层的重复实现 / 历史遗留空壳」，属于架构优化范畴：
  1. **alias 路由 handler 重复**：`proxy/router.py` 用 6 个 handler 实现 `/api/v1/*` 与 `/v1/*` 双路径，其中 `responses_alias`/`chat_completions_alias`/`models_alias` 三个 alias handler 与主 handler 逻辑 **100% 相同**（仅所属 router / 注释不同）。同一份逻辑写了 2 遍。
  2. **api/ 模块间重复私有 helper**：`_json_response`（keys.py 带 `status` 参数 + usage.py 固定 200 各一份）、`_get_recorder`（events.py 取 `event_recorder` + usage.py 取 `usage_recorder` 各一份）——「JSON 响应」与「从 app.state 取服务」两个模式各写了 2 份实现。
  3. **鉴权依赖空壳**：`api/auth.py` 的 `require_gateway_key_strict` 已退化为纯透传（`return await require_gateway_key(...)`，注释自承「不再有严格模式分支」）——历史遗留的冗余包装层，`keys.py`/`accounts.py` 共 7 处依赖它，但行为与 `require_gateway_key` 完全一致。
- **目标**：把上述三处收敛为单一实现——路由注册（双路径挂同一 handler）、API 依赖注入（统一 `api/_common.py`）、鉴权依赖（统一 `require_gateway_key`），结构更清晰、后续端点扩展不再复制样板；**接口行为零变化**。
- **非目标**：不对 `store/sqlite_store.py` 做拆分（665 行 18 方法跨 4 领域，但共享单连接、拆分会牵连全部调用方，属高风险大动作，收益不明确，本轮不做）；不改前端架构（G5 刚完成图表样板收敛，架构健康）；不引入任何新依赖（遵循 AGENTS.md）;不改任何 HTTP 路径、响应体、鉴权语义。

## 2. 摸底/可行性验证（已执行）

- **alias 重复确认**：逐行比对 `proxy/router.py`，`responses_alias` 与 `responses`、`chat_completions_alias` 与 `chat_completions`、`models_alias` 与 `models` 函数体逐一相同；唯一差异是 `@router.*` vs `@alias_router.*`。
- **helper 重复确认**：`api/keys.py:18-23`（`_json_response` 带 status）与 `api/usage.py:23-28`（`_json_response` 固定 200）、`api/events.py:13-17`（`_get_recorder` 取 event_recorder）与 `api/usage.py:16-20`（`_get_recorder` 取 usage_recorder）。
- **strict 空壳确认**：`api/auth.py:43-48` 实现为 `return await require_gateway_key(request, manager)`；引用面 `accounts.py`（3 处 Depends）+ `keys.py`（1 import + 3 处 Depends）；`tests/` 无直接引用。
- **双路由可行性验证（概念验证通过）**：同一函数连续叠 `@router.post` 与 `@alias_router.post` 两个装饰器，FastAPI 会将函数注册到两个 router——实测 `/api/v1/responses` 与 `/v1/responses` 均 200，`app.routes` 路径数不变。

## 3. 需求范围

### 3.1 功能需求

- [ ] FR1：`proxy/router.py` 的 `responses`/`chat_completions`/`models` 与对应 alias 合并称同一函数，用双路由装饰器同时挂 `/api/v1/*` 与 `/v1/*`；删除 `responses_alias`/`chat_completions_alias`/`models_alias` 三个函数。OpenAPI 中 6 条路径（3 主 + 3 alias）全部保留。
- [ ] FR2：新建 `api/_common.py`，收敛两处重复模式：
  - `json_response(data: dict, status: int = 200) -> Response`：统一 JSON 响应（keys.py 带 status 版与 usage.py 固定 200 版合并，支持默认 status）；
  - 通用「从 app.state 取服务」模板：为 `usage_recorder` / `event_recorder` 等提供统一取值函数（可参数化属性名，未初始化抛统一异常）。
  - `keys.py` / `usage.py` / `events.py` 全部改用 `_common`，删除各自私有 `_json_response`/`_get_recorder`。
- [ ] FR3：删除 `require_gateway_key_strict`；`keys.py` / `accounts.py` 的 import 与 `Depends` 全部改用 `require_gateway_key`。

### 3.2 非功能需求

- 兼容：HTTP 路径、请求/响应体、鉴权开关语义、OpenAPI schema 路径集合**零变化**。
- 结构：路由注册、API 依赖注入、鉴权依赖各收敛为单一实现点。
- 可维护：后续新增协议/端点不再复制 alias handler 与响应 helper 样板。

## 4. 接口定义

- 无对外 HTTP 变化。合并后路由注册示例（`proxy/router.py`）：

```python
@router.post("/responses")
@alias_router.post("/responses")
async def responses(request: Request) -> Response:
    """OpenAI Responses 透明转发（/api/v1 与标准 /v1 双路径）。"""
    return await _do_forward(request, "/responses")
```

- 新增模块 `api/_common.py` 仅在 api 包内部使用（下划线前缀包内私有）。

## 5. 验收标准

- [ ] AC1：`grep -r "responses_alias\|chat_completions_alias\|models_alias"` 全库 0 命中；OpenAPI（`app.openapi()["paths"]`）仍含 6 条路径（/api/v1/{responses,chat/completions,models} + /v1/{responses,chat/completions,models}）。
- [ ] AC2：`_json_response` / `_get_recorder` 从 keys/usage/events 移除、全走 `api/_common`；`grep -r "_json_response\|_get_recorder"` 0 命中。
- [ ] AC3：`require_gateway_key_strict` 全库 0 命中（定义 + 引用全部清理）；keys/accounts 鉴权行为不变（现有 `test_gateway_keys.py` / `test_accounts_api.py` 鉴权用例全过）。
- [ ] AC4：后端 `pytest` 全绿 + `ruff check src tests` 0 告警；双路径端点 `/api/v1/responses`、`/v1/responses`、`/api/v1/chat/completions`、`/v1/chat/completions`、`/api/v1/models`、`/v1/models` 回归均 200。
- [ ] AC5：前端零改动，`vitest` + `eslint` + `build` 全绿（回归确认）；三联动（PRD 已验收 + TODO G6 done + CHANGELOG）且 CI 三 job 全绿；README API 汇总同步（如需）。

## 6. 测试计划

- 复用既有：`test_proxy.py` / `test_proxy_errors.py` 覆盖 `/api/v1` 与 `/v1` 双路径转发（FastAPI TestClient）；`test_gateway_keys.py` / `test_accounts_api.py` 覆盖鉴权依赖合并后行为。
- 新增断言：测试 `create_app()` 后 `openapi()["paths"]` 含 6 条路径（防 alias 收敛丢失路径）。
- 手动：`python -m pytest -p no:cacheprovider`；`ruff check src tests`。
- 前端：`vitest run` + `eslint` + `pnpm build`（零改动回归）。

## 7. 里程碑与估算

| 子任务 | 预估 |
|---|---|
| router.py alias 合并（双路由装饰器） | 10 分钟 |
| api/_common.py 新建 + keys/usage/events 迁移 | 20 分钟 |
| strict 合并 + accounts/keys 引用更新 | 10 分钟 |
| 验证（pytest/ruff/openapi 断言/前端回归） | 20 分钟 |
| 文档同步 + 三联动 + CHANGELOG | 10 分钟 |

## 8. 风险与对策

| 风险 | 对策 |
|---|---|
| 双路由装饰器改变 OpenAPI 路径/operationId | 概念验证已确认两路径均注册；AC1 openapi 断言兜底 |
| alias 合并后函数名/路由重复冲突 | 同一函数叠两装饰器（已验证）；删除陈旧 alias 函数 |
| strict 合并引入鉴权行为差异 | strict 本就是纯透传，逐条核对 7 处引用改 `require_gateway_key`；现有鉴权用例回归 |
| api/_common 收敛破坏现有响应格式 | 函数签名对齐（json_response 支持 status 默认 200），响应字节与现有一致 |
| 拆分 sqlite_store 诱惑（范围蔓延） | 明确列入非目标，不在本阶段开展 |

## 9. 变更记录

| 日期 | 变更内容 | 理由 |
|---|---|---|
| 2026-08-21 | 初始定稿 | — |
| 2026-08-21 | 实现完成：① proxy/router.py 的 `responses`/`chat_completions`/`models` 与 alias 合并为同一函数叠 `@router.*`/`@alias_router.*` 双路由装饰器，删除 3 个 alias handler；② 新建 api/_common.py（json_response + get_state_service），keys/usage/events 删除各自 `_json_response`/`_get_recorder` 改走 `_common`；③ 删除 `require_gateway_key_strict` 空壳，accounts.py（3 处依赖）/keys.py（import+3 处）改用 `require_gateway_key`。openapi 6 条路径全保留；grep 六项模式 0 命中；pytest 138 + ruff 0；独立实例双路径回归（models 内容一致、四条转发路径可达）；前端 vitest 60 + eslint 0 + build 全绿（零前端改动） | 阶段 G6 开发 |
