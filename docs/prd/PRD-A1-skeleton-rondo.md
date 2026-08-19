# PRD-A1-仓库骨架与Rondo规范落地

> 状态生命周期：草稿 → 评审 → approved（定稿）→ 开发中 → 已验收

## 元信息

| 字段 | 值 |
|---|---|
| 阶段 | A1 |
| 名称 | 仓库骨架 + Rondo 规范落地 |
| 状态 | approved |
| 创建日期 | 2026-08-19 |
| 定稿日期 | 2026-08-19 |
| 验收日期 | — |
| 关联文档 | docs/TODO.yaml 阶段 A1 |

## 1. 背景与目标

- **背景**：OpenCode Go 多账号合并代理是新项目，需要先把仓库骨架与 Rondo 开发规范落地，让后续所有阶段在约束体系内推进（PRD 驱动、TODO 清单、全 PR 流、hooks 强制）。
- **目标**：仓库具备规范骨架——AGENTS.md / TODO.yaml / PROCESS.md / PRD 模板 / githooks 全部就位且 hooks 已启用，git 主干（main + develop）就绪，CHANGELOG / .gitignore / README 就位。
- **非目标**：不实现任何代理业务逻辑（账号池/转发/切换属 B 阶段）；不搭前端/后端代码骨架（属 A2 / A3）；不配置 GitHub Actions（属 G1）。

## 2. 需求范围

### 2.1 功能需求

- [ ] FR1：仓库根含 AGENTS.md，覆盖工作方式 / 代码风格（Python+TS）/ Git Flow 全 PR 流 / PRD 驱动 / 安全边界 / 跨平台兼容，含本项目 UI 设计规范（白色简洁、无阴影、无圆角）。
- [ ] FR2：docs/TODO.yaml 定义阶段与步骤（A 地基 / B 代理核心 / C 监控台 / G 收尾），每个步骤含 modules 与 acceptance，状态图例明确；A1 标 in_progress。
- [ ] FR3：docs/PROCESS.md 为六步闭环推进办法；docs/prd/PRD-TEMPLATE.md 为 PRD 模板（含变更记录小节）。
- [ ] FR4：.githooks/ 含 commit-msg（提交规范校验）、pre-push（main/develop 全 PR 流保护）、check_commit_msg.py（type 白名单 / 阶段存在性 / feat 带 PRD / 分支名交叉校验），裁剪点已按本项目模块定制。
- [ ] FR5：git 主干就绪：main 为初始提交基底，develop 从 main 建立；`git config core.hooksPath` 指向 .githooks。
- [ ] FR6：CHANGELOG.md（[未发布] 小节）、.gitignore（排除 .env / 密钥 / 构建产物 / 本地数据）、README.md（项目定位 / 目录结构 / 规范入口 / 合规边界）就位。

### 2.2 非功能需求

- 安全：.gitignore 排除 .env 与密钥；README 与 AGENTS 声明合规边界。
- 兼容性：文档与 hook 脚本跨平台可用（sh hook 依赖 Git Bash，Windows 环境已具备）。

## 3. 技术方案

- 目录：`docs/`（TODO.yaml、PROCESS.md、prd/）、`.githooks/`、根级 AGENTS.md / CHANGELOG.md / .gitignore / README.md。
- hooks 复用 Rondo 方法资产（minimal-blog 仓库 public/assets/rondo-method/），裁剪点：MODULE_SCOPES 改本项目模块（backend/web/accounts/proxy/rotation/store/dashboard/charts/docs/tests/release）。
- 阶段规划：A 地基（A1 骨架 / A2 后端 / A3 前端）、B 代理核心（B1 账号池 / B2 转发 / B3 切换 / B4 持久化）、C 监控台（C1 大盘 / C2 图表）、G 收尾（G1 CI / G2 文档）。

## 4. 接口定义

- TODO.yaml 结构：`stages[].id/name/steps[]`，步骤含 id/title/status/prd/prd_status/modules/acceptance。
- 提交规范：`<type>(<scope>): <subject>`（subject 中文）；feat/fix/prd/todos 的 scope 必须是 TODO 阶段 id。

## 5. 验收标准

- [ ] AC1：`git config core.hooksPath` 输出 `.githooks`。
- [ ] AC2：`git branch` 含 main 与 develop。
- [ ] AC3：`.githooks/check_commit_msg.py` 中 MODULE_SCOPES 含 backend/web/accounts 等本项目模块。
- [ ] AC4：docs/TODO.yaml 可被 PyYAML 解析，阶段 id 集合含 A1/A2/A3/B1/B2/B3/B4/C1/C2/G1/G2。
- [ ] AC5：AGENTS.md / PROCESS.md / PRD-TEMPLATE.md / CHANGELOG.md / .gitignore / README.md 均存在且内容非模板占位符。
- [ ] AC6：git 仓库首次提交（main）包含上述全部文件；.env 未入库。

## 6. 测试计划

- 单元：`check_commit_msg.py` 用 python 直接调用验证拒绝/放行路径（后续阶段补 pytest 化）。
- 手动：模拟一次非法 commit message 被拒绝（hook 生效证据）；模拟 feature 直推 develop 被拒绝。

## 7. 里程碑与估算

| 子任务 | 预估 |
|---|---|
| 目录 + git init + 主干 | 5 分钟 |
| 规范文件落地与裁剪 | 20 分钟 |
| hooks 启用与自测 | 10 分钟 |

## 8. 风险与对策

| 风险 | 对策 |
|---|---|
| sh hook 在 Windows 需要 Git Bash | 环境已装 Git Bash；commit-msg 校验核心在 Python，跨平台 |
| 模板资产路径错误 | 从 minimal-blog 仓库本地资产复制，已验证存在 |
| 阶段规划过早固化 | 阶段是路线图而非承诺，后续按 PRD 变更双路径调整 |

## 9. 变更记录

| 日期 | 变更内容 | 理由 |
|---|---|---|
| 2026-08-19 | 初始定稿 | — |
