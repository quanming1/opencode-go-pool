# 使用手册（usage）

从零配置到代理可用 + 大盘可视化的完整操作路径。

## 1. 配置账号

### 1.1 配置文件

```bash
cd apps/backend
copy config\accounts.example.yaml config\accounts.yaml
```

编辑 `config/accounts.yaml`，每个账号一条：

```yaml
accounts:
  - id: opencode-go-1
    name: OpenCode Go 主账号
    api_key: ${OPENCODE_GO_KEY_1}      # 引用环境变量，不落明文
  - id: opencode-go-2
    name: OpenCode Go 备用账号
    api_key: ${OPENCODE_GO_KEY_2}
    # 可选字段：
    # models: [gpt-5.6-luna]           # 限制可用模型（空 = 全部）
    # enabled: false                    # 启动即禁用
    # base_url: https://xxx/v1          # 覆盖全局上游地址
```

### 1.2 设置密钥

推荐写入 `apps/backend/.env.keys`（账号密钥专用文件，不入库）：

```bash
# apps/backend/.env.keys
OPENCODE_GO_KEY_1=sk-xxxxxxxx
OPENCODE_GO_KEY_2=sk-xxxxxxxx
```

或临时用进程环境变量（优先级高于 .env.keys）：

```bash
# Windows（当前会话）
set OPENCODE_GO_KEY_1=sk-xxxxxxxx
```

> 说明：`${VAR}` 引用解析顺序 = 进程环境变量 > `apps/backend/.env.keys` 文件。注意密钥文件是 `.env.keys`（不是 `.env`）——`.env` 是应用配置（Settings 严格模式），两者职责分离。引用缺失时该账号被跳过（日志有警告），不影响其他账号。密钥只存在内存与本地文件，绝不写入日志或 API 响应。

## 2. 启动

```bash
# 后端（终端 1）
cd apps/backend
.venv\Scripts\python -m uvicorn opencode_pool.app:app --host 127.0.0.1 --port 48700

# 前端（终端 2）
cd apps/web
pnpm dev
```

## 3. 验证

### 3.1 健康检查

```bash
curl http://127.0.0.1:48700/health
# {"status":"ok","version":"0.1.0"}
```

### 3.2 账号列表（脱敏）

```bash
curl http://127.0.0.1:48700/api/accounts
# {"accounts":[{"id":"opencode-go-1","name":"...","status":"healthy",...}]}
```

### 3.3 发起一次 Responses 转发

```bash
curl http://127.0.0.1:48700/api/v1/responses ^
  -H "Content-Type: application/json" ^
  -d "{\"model\":\"gpt-5.6-luna\",\"input\":\"hi\",\"stream\":false}"
```

成功响应携带 `X-Pool-Account` 响应头（本次使用的账号 id）。流式请求把 `"stream"` 改为 `true`（SSE 逐块透传）。

### 3.4 查看统计与切换历史

```bash
curl http://127.0.0.1:48700/api/stats
curl http://127.0.0.1:48700/api/switch-history
```

### 3.5 大盘可视化

浏览器打开 `http://localhost:48701`：

- 顶部统计卡：可用 / 冷却中 / 已禁用；
- 账号卡片：状态徽章、冷却剩余、连续/累计失败、最近错误；
- 用量趋势图：近 24h 请求量与 Token（每 10s 自动刷新）；
- 轮换事件时间线：何时哪个账号被冷却/恢复/禁用（中文语义标签）。

## 4. 接入客户端（如 ftre）

在客户端的 LLM 配置中把 provider 指向本代理：

```json
{
  "api_base": "http://127.0.0.1:48700/v1",
  "api_key": "任意值（代理不做鉴权）",
  "model": "gpt-5.6-luna"
}
```

> 协议：代理透明转发两种 OpenAI 协议，不做协议转换——`POST /v1/responses`（Responses 协议，如 muse-spark / gpt-5.6-luna）与 `POST /v1/chat/completions`（Chat Completions 协议，如 kimi / minimax / glm / deepseek）。客户端按模型选择对应端点（与直连 OpenCode 相同）。

## 5. 常见问题

### 账号被自动禁用了怎么办？

连续失败达到阈值（默认 3 次，`MAX_CONSECUTIVE_FAILURES` 可调）会 `auto-disabled`——这是防止坏账号被反复尝试的保护。检查该账号密钥是否失效/上游是否恢复后，重启后端（恢复 healthy）或手动改 SQLite `accounts` 表 `enabled=1`。

### 冷却是怎么恢复的？

三个路径：① 后台扫描（默认 60s 一次，`POOL_SCAN_INTERVAL_SECONDS`）；② 下次选号时惰性检查；③ 上游给了 `Retry-After` 头时按其秒数冷却（优先于默认 5 小时）。

### 数据会丢吗？

账号状态、切换历史、用量统计都持久化在 `data/opencode_pool.db`（SQLite），重启自动恢复。DB 路径不可写时服务照常运行（纯内存，日志有警告），修好路径后重启即可。

### 流式请求的 token 统计是 0？

流式 SSE 的 token 无法在不解析全流的情况下精确提取（PRD-C2 明确边界）：流式成功只计请求数，非流式精确记录 prompt/completion tokens。

### 为什么我的客户端 400 / 401 不重试？

按设计：400（请求本身问题）不 mark_down 不重试——换账号也一样失败；401（密钥失效）mark_down 但不重试——该账号的问题换号前应先修密钥。429/限流/5xx/网络错误才会自动切换下一个账号。
