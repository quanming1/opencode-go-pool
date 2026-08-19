# OpenCode Go Pool 项目开发规则（AGENTS.md）

> 本文件是对**所有 AI agent**（Claude Code / Cursor / 其他协作 agent）以及人类协作者的行为规范。
> 任何人在仓库动手前，必须完整阅读并遵守本文件。

## 1. 项目概况

- **OpenCode Go Pool**：多个 OpenCode Go 订阅账号合并为一个逻辑上游的代理服务——账号池管理、5 小时窗口追踪、额度耗尽自动切换；配套可视化监控台。
- 当前阶段：见 `docs/TODO.yaml` 的状态标记
- 关键文档：
  - `docs/TODO.yaml` — 结构化 TODO 清单（**开发的唯一执行依据**）
  - `docs/PROCESS.md` — 推进管理办法（六步闭环）
  - `docs/prd/` — 阶段 PRD（每个阶段一份，PRD 是开发的唯一依据）

## 2. 目录结构

```
opencode-go-pool/
├─ apps/
│  ├─ backend/     Python 3.12 + FastAPI（代理核心：账号池 / 路由 / 转发）
│  └─ web/         React + Vite + TypeScript + ECharts（监控台）
├─ docs/           TODO.yaml / PROCESS.md / prd/
└─ .githooks/      提交与推送校验（本地强制）
```

## 3. 工作方式

1. **严格按 `docs/TODO.yaml` 的阶段顺序推进，不跳步、不越权**——每步只做该步清单内的任务。
2. 每阶段完成标准：代码 + 测试 + 文档 + 可独立验收（对照 TODO 中的「验收」条目）。
3. 动手前先读相关文档与现有代码，遵循已有模式与风格；不另起一套并行模式。
4. 不引入未声明的依赖；用任何库前先确认已在依赖清单声明（pyproject.toml / package.json）。
5. 只改任务范围内的文件；不做用户没要求的额外改动。
6. 同一问题反复改不好就停下，回到初始假设重新判断，换方向。

## 4. 代码风格

- 后端：Python 3.12，**类型注解完整**；格式化 ruff（line-length 100），导入排序 ruff；命名 snake_case。
- 前端：TypeScript strict；格式化 prettier + eslint；命名 camelCase（组件 PascalCase）。
- 每个模块文件头部有注释说明职责。
- **注释要求**：复杂逻辑必须写注释，注释写「为什么」而非「是什么」。
- **语言规范**：所有注释、提交信息、文档统一使用中文；代码标识符保持英文。
- **禁用 emoji**：代码、注释、文档、提交信息、终端输出一律不使用 emoji；状态用文字或 ASCII 标记（[x] / [ ]）。

## 5. UI 设计规范（前端强制）

- **白色简洁风**：背景纯白（#FFFFFF），正文深灰/纯黑，边框浅灰（#E5E7EB）细线。
- **禁止阴影**：任何元素不得使用 box-shadow / drop-shadow。
- **禁止圆角**：所有 border-radius 一律 0（直角）。
- 间距与排版服务于信息密度；图表统一 ECharts（主题同样无阴影无圆角）。
- 颜色只允许白 + 灰阶 + 单一强调色（语义状态色除外）。

## 6. Git Flow 规范（强制）

### 6.1 分支模型

```
main            ← 仅存放可发布版本（受保护语义：永不直接提交）
  └─ develop    ← 日常集成分支（默认工作基底）
       ├─ feature/<阶段id>-<name>   新功能 / 新任务
       ├─ release/<ver>             发布准备（版本号冻结、回归测试）
       └─ hotfix/<name>             生产紧急修复（从 main 切出，修完回灌 main + develop）
```

### 6.2 分支规则

- 默认工作分支是 **develop**；main 永不直接提交；**develop 同样禁止任何本地提交/merge——全 PR 流：develop 只接受 GitHub PR 服务器端合入，本地 develop 永远只 `pull` 同步**（pre-push hook 强制）。
- 每个任务/功能开独立分支：`git checkout -b feature/<阶段id>-<short-name> develop`，**feat/fix 分支名必须关联 TODO 阶段 id**（如 `feature/B1-rotation`）。
- **交叉校验**：feat/fix 提交的 scope 必须与分支名中的阶段 id 一致（commit-msg hook 强制）。

### 6.3 提交规范（Conventional Commits）

```
<type>(<scope>): <subject>
```

- **subject 使用中文**（type/scope 保持英文）。
- type：`feat` / `fix` / `prd` / `todos` / `docs` / `refactor` / `test` / `style` / `chore` / `perf`
- **scope 分三类**：
  - `feat` / `fix` / `prd` / `todos`：scope **必须**是 TODO 阶段标识（如 `B1`），且**必须真实存在于 `docs/TODO.yaml`**（commit-msg hook 强制校验）。
  - `feat` 额外强制：暂存必须包含对应阶段 PRD（`docs/prd/PRD-<scope>-*.md`）——行为变更必须同步 PRD 变更记录。
  - `perf`：scope 必须带 FR 引用（`perf(B2-FR3)`），引用的 FR 编号必须真实存在于对应 PRD。
  - 其他 type：scope 用模块名（见 `check_commit_msg.py` 顶部「裁剪点」）。
- **一条提交只做一件事**；禁止 `fix stuff`、`update`、`misc` 这类无意义 message。
- 提交前自查：`git status` 确认无多余文件；`git diff` 通读改动。

### 6.4 合并策略

- `feature/*` → `develop`：**一律走 GitHub PR/MR（Code Review）**——push 分支后提 PR，**禁止本地 `git merge --no-ff` 合并回 develop**（pre-push hook 强制）。
- **develop 只接受 PR 合入**：本地 develop 永远只 `pull` 同步。
- **develop 与 main 之间同样禁止本地直接 merge，一律走 GitHub PR**：develop → main 走 `release/*` 分支提 PR；main → develop 的 hotfix 回灌同样走 PR。
- **禁止 rebase 重写已推送历史**。

### 6.5 版本与 tag

- 语义化版本 SemVer：`MAJOR.MINOR.PATCH`。
- 每次发布在 main 打 tag：`v<version>`。
- 版本号集中管理：后端 `apps/backend/pyproject.toml`；前端 `apps/web/package.json`（发布时同步 bump）。

### 6.6 禁止事项

- 直接向 main 提交 / 推送代码。
- **本地 `git merge` 任何分支到 develop**。
- 把 secrets / API key / 配置文件提交进仓库（账号 Key 只存本地 `.env` 或系统环境变量，`.gitignore` 已排除）。
- 遗留临时文件、调试代码、`.bak`、未使用的死代码。

### 6.7 本地保护（pre-push hook）

- 仓库内置 `.githooks/pre-push`：
  - **禁止把非 main 分支直接 push 到 main**（发布推送除外；禁止删除远程 main）。
  - **全 PR 流保护 develop**：禁止删除远程 develop；禁止 feature 直推 develop；develop 本地领先远程即拒绝。
- clone 后执行一次：`git config core.hooksPath .githooks`。
- **AI agent 与人同规则**。

### 6.8 标准流程（每次任务）

```bash
git checkout develop && git pull          # 1. 同步基底
git checkout -b feature/<阶段id>-<task>    # 2. 开任务分支
# ... 开发 + 本地测试 ...
git add <改动文件>                          # 3. 提交（conventional）
git commit -m "feat(B1): 描述"
git push origin feature/<阶段id>-<task>    # 4. 推送 feature 分支
# ... GitHub 提 PR：feature → develop ...
git checkout develop && git pull          # 5. PR 合入后同步
```

## 7. 测试

- 后端：pytest（`apps/backend/tests/`）；每个新功能必须配测试；每个 bug 修复必须配回归测试。
- 前端：vitest（关键逻辑组件）。
- 提交/合并前本地必须通过：后端 `pytest` + `ruff`；前端 `eslint` + `vitest` + `build`。
- 测试不依赖真实外部凭据——OpenCode 上游用 mock / fake（respX 或自建 fake server）。

## 8. 文档

- 新模块 / 行为变更必须同步更新 `docs/` 与 `README.md`。
- **日志与变更记录（强制）**：每次功能 / 修复完成，必须同步更新 `CHANGELOG.md`（追加到 `[未发布]` 对应小节）。
- 提交历史是项目的执行日志：commit message 必须可追溯（对应 TODO 条目）。

## 9. PRD 驱动开发（强制）

- **先 PRD，后开发**：每个 TODO 阶段开工前，必须先在 `docs/prd/` 创建对应 PRD（从 `PRD-TEMPLATE.md` 复制），评审定稿（状态 `approved`）后才能开发。
- **PRD 是开发的唯一依据**：需求、实现、测试、验收全部对照 PRD；禁止开发 PRD 未定义的内容；范围变更必须走 PRD「变更记录」。
- **验收按 PRD 标准**：每阶段完成必须按 PRD「验收标准」逐条核对，全部通过才算完成。
- **生命周期状态机（强制）**：`草稿 → approved（评审定稿） → 开发中 → 已验收`，禁止跳变（approved / 已验收必须留档日期）。TODO.yaml 立项即标 `in_progress`，验收通过才 `done`。
- **收尾三联动（强制）**：阶段收尾 = PRD 标 `已验收` + TODO 标 `done` + CHANGELOG 追加，三者缺一不可。
- **变更双路径**：需求变更先判断——属于原 PRD 范围（同阶段/同主题/对原 FR·AC 的修正细化）→ 修改正文 + **MUST 在末尾「变更记录」追加（日期+变更+理由）** + 重核受影响 AC；超出范围 / 新阶段 / 全新主题 → 新开 PRD 走完整闭环。
- 推进管理办法详见 `docs/PROCESS.md`。

## 10. 安全与边界

- **不引入 / 记录 secrets**：OpenCode Go API Key 只存本地 `.env`（已 .gitignore）或环境变量，示例文件只放占位符。
- **合规边界**：只支持官方 API Key 的合法接入与故障切换；不实现 Cookie 抓取、Session 复用、凭证伪造、对外转售额度等行为。
- 日志脱敏：API Key 全量输出一律打码（如 `sk-****abcd`）。

## 11. 兼容性要求（强制）

- 跨平台（Windows / Linux / macOS）：路径用 pathlib / path.join，不硬编码分隔符与盘符；源文件统一 LF 换行。
- 编码：文件读写显式 `encoding="utf-8"`；禁止向终端 / 文件输出乱码。
- 不在工作区留临时文件；调试产物放系统临时目录，用完即清。
