# 安全审查报告（私密信息审计）

审查时间：2026-08-20
审查范围：opencode-go-pool（开源前置检查）
审查结论：**通过，无 secret 泄露**

## 扫描范围与方法

| 范围 | 方法 | 结果 |
|---|---|---|
| 已追踪文件（工作区） | 遍历 `git ls-files` 全部文件，正则匹配 `sk-`/`gk-` 长串、`GATEWAY_MASTER_KEY=` 明文定义、`Authorization: Bearer` 明文、YAML `api_key:` 直填 | 6 处命中，全部为文档/代码中的占位符示例（`Bearer <key>`、`Bearer gk-xxx` 等）与中文描述误报，**无真实 key** |
| git 全历史 blob | `git rev-list --objects --all` 枚举全部 689 个文本对象并逐一内容匹配 | 14 处命中，均为上述同一批占位符文本；**无真实 key** |
| 已知 key 指纹 | 以本会话聊天中出现过的 6 把上游 `sk-` key 与 2 把网关 `gk-` key 的前 12 字符做精确子串比对 | **0 命中** |
| git stash | `git stash list` | 为空 |
| remote 凭据 | `git remote -v` | https 纯 URL，无内嵌凭据 |

## 排除项核对（gitignore 生效确认）

以下本机敏感文件均已由 `.gitignore` 排除，确认不在 `git ls-files` 中：

- `apps/backend/.env`（应用配置）
- `apps/backend/.env.keys`（账号密钥 + `GATEWAY_MASTER_KEY` + `GATEWAY_AUTH`）
- `apps/backend/config/accounts.yaml`（6 个账号的真实密钥映射，仅 `apps/backend/.env.example` 作为模板入库）
- `apps/backend/data/`、`*.db`（本地 SQLite 数据）

## 风险评估

- 仓库当前为 private；转为 public 后以上排除项仍不会随仓库发布。
- `.env.example` 为占位符模板（`sk-xxx`），可安全公开。
- 已知 key（聊天记录中全文出现过）未进入任何 git 对象，**无历史泄露**；但出于纵深防御，仍建议在开源前后对上游 OpenCode Go key 做一次轮换（成本低，防聊天侧泄露面）。
- 日志/事件表中理论上可能积累过脱敏的 key 痕迹（`mask_api_key` 仅保留末 4 位），事件 `data` 字段不写明文 key，风险可接受。

## 建议

1. 开源前将 GitHub 仓库改为 public（需在仓库 Settings 操作或 `gh repo edit --visibility public`）。
2. 如需最高安全等级，可轮换 6 把上游 key 并同步更新 `apps/backend/.env.keys` 与 `.env`。
3. 后续开发保持「密钥只存本地 `.env.keys`/`.env`（已 gitignore）」的约定。