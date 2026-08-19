# PRD-B2-Responses协议透明转发

> 状态生命周期：草稿 → 评审 → approved（定稿）→ 开发中 → 已验收

## 元信息

| 字段 | 值 |
|---|---|
| 阶段 | B2 |
| 名称 | Responses 协议透明转发 |
| 状态 | approved |
| 创建日期 | 2026-08-19 |
| 定稿日期 | 2026-08-19 |
| 验收日期 | — |
| 关联文档 | docs/TODO.yaml 阶段 B2；docs/prd/PRD-B1-accounts-pool.md |

## 1. 背景与目标

- **背景**：B1 已实现账号池与状态机，但还没有"把多个账号合并成一个逻辑上游"的转发层。B2 在账号池之上加一个 OpenAI Responses 兼容端点：客户端（ftre）只面向代理一个地址，代理负责选号、转发、失败切换、账号状态联动。
- **目标**：代理暴露 `POST /api/v1/responses`，收到 OpenAI Responses 请求后，从账号池选一个 healthy 账号，把请求转发到该账号配置的上游，并支持（a）SSE 流式透传与（b）非流式 JSON 透传；上游明确限流/额度错误时 `mark_down` 该账号并重试下一个；所有日志与错误信息不含明文密钥。
- **非目标**：不做协议转换（本代理只做 Responses → Responses 透传，不做 Chat Completions ⇄ Responses 互转）；不主动轮询额度（B3 完善错误分类定时恢复）；不做持久化（B4）；不实现客户端鉴权（本地单机部署，信任内网调用方）。

## 2. 需求范围

### 2.1 功能需求

- [ ] FR1：端点 `POST /api/v1/responses`：接收任意 OpenAI Responses 请求体（含 `stream`、`input`、`instructions`、`tools`、`reasoning` 等字段），透传语义不加删改字段（仅替换认证与目标地址）。
- [ ] FR2：选号：请求到达时调用 `AccountPool.pick_next()` 选当前 healthy 且 enabled 的账号；无账号可用时返回 503（JSON 错误，可含 `error.message`）。
- [ ] FR3：上游地址解析：每个账号可选 `base_url`；缺省用全局配置 `UPSTREAM_BASE_URL`（env / 配置默认 `https://api.opencode.ai/v1`）。认证头替换为该账号 `api_key`。
- [ ] FR4：非流式（`stream: false`）：透传上游完整 JSON 响应（状态码 + body），同时在响应头加 `X-Pool-Account: <account_id>` 便于追踪。
- [ ] FR5：流式（`stream: true`）：建立上游 SSE 连接，逐块转发（`text/event-stream`），客户端断开/POST 请求关闭时终止上游请求；透传上游状态码与响应头（Content-Type）。
- [ ] FR6：失败切换（B2 语义，不做中途切换）：
  - 上游**连接失败 / 5xx / 明确限流（429）**且在**首字节未发出**前 → `mark_down` 当前账号（reason 分类）→ 选下一个账号重试，最多重试 remaining healthy 账号数（一个账号一次）；
  - 上游 **400 级（请求本身问题）** / 401（该账号密钥失效也 mark_down，但**不重试**，直接返回错误）；
  - **流式已发出首字节后**的断流：不重试，把上游中断透传为流结束（避免重复文本/工具调用）。
- [ ] FR7：错误分类函数 `classify_upstream_status(status: int, body: str) -> ErrorKind`：`quota`（429 / quota / rate limit 关键词）、`auth`（401/403）、`bad_request`（400-499 其余）、`server`（5xx / 连接错误）、`ok`。
- [ ] FR8：日志与错误脱敏：不打印任何账号 api_key；上游 URL 打印时去掉 query 中可能含的密钥片段；响应错误体透传不落日志（只落状态码与分类）。

### 2.2 非功能需求

- 性能：流式转发为增量转发，不缓冲整包；非流式上游响应大小不做硬限制（透传）。
- 健壮性：上游连接空闲超时默认 60s（可配置）；整体请求不做额外超时（透传上游语义）。
- 兼容性：透传层不解析/不校验请求体结构，仅需区分 `stream` 布尔；对新版 Responses 字段天然兼容。
- 可测：所有上游交互走注入的 HTTP client（httpx.AsyncClient），单测用 fake 上游 server（ASGI / httpx MockTransport）。

## 3. 技术方案

- 新增目录/文件：

```
apps/backend/src/opencode_pool/
├─ proxy/
│  ├─ __init__.py          # 导出 ProxyRouter、create_proxy_router
│  ├─ router.py            # fastapi.APIRouter：/api/v1/responses 与 /api/v1/models
│  ├─ forwarder.py         # Forwarder：选号/转发/切换/分类（核心）
│  └─ errors.py            # classify_upstream_status / ErrorKind / ProxyError
└─ api/v1.py               # FP：挂载 proxy router（或 proxy/router 自带 prefix）
```

- `Forwarder` 核心流程（流式/非流式共用选号与错误处理）：

```python
async def forward(request) -> Response:
    attempts = pool.healthy_count()          # 至多每个 healthy 账号尝试一次
    for _ in range(attempts):
        account = pool.pick_next()
        if account is None: break
        try:
            return await self._do_forward(account, payload, stream)
        except UpstreamError as e:
            pool.mark_down(account.id, e.kind + ": " + (e.detail or ""))
            if e.kind in (ErrorKind.BAD_REQUEST, ErrorKind.AUTH):
                return self._error_response(e)   # 不重试
            # quota / server / network → 继续下一个账号
    return error_response(503, "no healthy account available")
```

- 流式转发用 `httpx.AsyncClient.stream()` + `Response.content` 的异步迭代：

```python
async with client.stream("POST", url, json=payload, headers=auth, timeout=...) as up:
    resp = StreamingResponse(up.aiter_raw(), status_code=up.status_code, media_type="text/event-stream")
    resp.headers["X-Pool-Account"] = account.id
    return resp
```

注意：首字节前失败（ConnectError / status 4xx/5xx）需要在打开流时捕获；用 `up.aiter_raw()` 前先 await `up.aread()` 判定状态，再决定走流式透传还是错误处理。

- 依赖：httpx 已是 dev 依赖；提升为 runtime 依赖（`httpx>=0.27`）。
- 配置：`UPSTREAM_BASE_URL`（env，默认 `https://api.opencode.ai/v1`）、账号可选 `base_url` 覆盖。B4 持久化前 UPSTREAM_BASE_URL 进 config.py Settings。

## 4. 接口定义

- `POST /api/v1/responses`：

```jsonc
// request（原样透传，示例）
{ "model": "gpt-5.6-luna", "input": "hi", "stream": true, "reasoning": {"effort": "high"} }
```

成功响应：非流式 = 上游 JSON 透传 + `X-Pool-Account`；流式 = `text/event-stream` 增量 + `X-Pool-Account`。
失败（无可用账号）：503 `{"error": {"message": "no healthy account available"}}`。
上游 429/5xx 且全部账号失败：最终返回最后一个上游的错误状态码 + 透传 `{"error": {...}}`。

- `GET /api/v1/models`：返回账号池合并的模型清单（B2 先返回上游 models 聚合；若账号未配 models 则返回空列表 + 提示）。

## 5. 验收标准

- [ ] AC1：`pytest` 全绿（新增 test_proxy.py 覆盖非流式/流式/切换/脱敏）。
- [ ] AC2：`ruff check src tests` 无警告。
- [ ] AC3：单 fake healthy 账号：`POST /api/v1/responses`（stream=false）透传上游 JSON 且响应头含 `X-Pool-Account`。
- [ ] AC4：单 fake healthy 账号：`stream=true` 时客户端收到 `text/event-stream` 逐块数据，block 顺序与上游一致。
- [ ] AC5：两账号（前一个上游返回 429、后一个 healthy）：请求被转发到第二个账号，首个账号 status=cooldown 且 error_kind 记录为 quota。
- [ ] AC6：请求体 400（上游 400）：不 mark_down、不重试，直接返回错误。
- [ ] AC7：全部账号不可用（或全被限流）→ 503，错误体含 "no healthy account"。
- [ ] AC8：日志与错误体不出现任何明文 api_key（用脱敏断言抓 grep）。
- [ ] AC9：`UPSTREAM_BASE_URL` 可配置；未配置走默认值。

## 6. 测试计划

- 单测：`classify_upstream_status` 各分类；`Forwarder` 用 `httpx.AsyncClient(transport=MockTransport(...))` 注入 fake 上游序列（429→200、400、网络错）。
- 集成：TestClient 打 `/api/v1/responses`（非流式）；流式用 TestClient stream + 累计 body 断言 SSE 事件顺序。
- 脱敏：构造含明文 key 的上游错误体，断言日志无 key；`X-Pool-Account` 存在。

## 7. 里程碑与估算

| 子任务 | 预估 |
|---|---|
| errors.py 分类 + forwarder.py | 30 分钟 |
| router.py + 挂载 + 配置 | 20 分钟 |
| 单测（fake 上游序列） | 40 分钟 |
| 集成 + 流式断言 + 脱敏 | 30 分钟 |

## 8. 风险与对策

| 风险 | 对策 |
|---|---|
| 流式首字节前错误难判定 | 打开流后先 `await aread()` 判定状态码，非 2xx 走错误分支 |
| 中途断流重复文本 | B2 明确不重试单流；工具调用切换由下一轮请求天然完成 |
| 上游 URL / 协议假设有误 | UPSTREAM_BASE_URL 可配置 + fake 上游测试，不绑定真实地址 |
| ReAct 多轮同一请求内多次调用 | B2 每次 `POST /responses` 独立选号 = 天然跨账号轮换 |

## 9. 变更记录

| 日期 | 变更内容 | 理由 |
|---|---|---|
| 2026-08-19 | 初始定稿 | — |
