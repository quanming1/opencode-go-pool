# PRD-G1-CI持续集成

> 状态生命周期：草稿 → 评审 → approved（定稿）→ 开发中 → 已验收

## 元信息

| 字段 | 值 |
|---|---|
| 阶段 | G1 |
| 名称 | CI 持续集成 |
| 状态 | approved |
| 创建日期 | 2026-08-20 |
| 定稿日期 | 2026-08-20 |
| 验收日期 | — |
| 关联文档 | docs/TODO.yaml 阶段 G1；.github/workflows/ci.yml |

## 1. 背景与目标

- **背景**：项目 A-C 阶段积累了大量代码与测试（后端 pytest / ruff，前端 eslint / vitest / build），但全部靠本地手动跑——没有服务器端持续校验。Rondo 规范要求"测试/构建必须由 forces 保证"，GitHub Actions 能自动在 PR 与 push 时跑全套校验，防止回归合入。
- **目标**：仓库拥有 GitHub Actions CI：任意 push/PR 触发，后端跑 pytest + ruff，前端跑 eslint + vitest + build；全部绿才允许合入 develop。
- **非目标**：不做覆盖率上传/阈值（后续可加）；不做自动发布流水线（release 目前走本地流程）；不做 Windows/macOS 矩阵（当前单平台 linux，够用且省时；跨平台是 AGENTS 的理想，现阶段以 CI 绿为准）。

## 2. 需求范围

### 2.1 功能需求

- [ ] FR1：`.github/workflows/ci.yml`：`on: push + pull_request`（branches: develop、main、feature/*）。
- [ ] FR2：后端 job：setup-python 3.12 + `pip install -e "apps/backend[dev]"` + `ruff check` + `pytest -q`（工作目录 apps/backend）。
- [ ] FR3：前端 job：setup-node 20 + `pnpm install`（apps/web）+ `eslint` + `vitest run` + `build`。
- [ ] FR4：并发/失败快速失败：两个 job 并行，任一失败则 workflow 红。
- [ ] FR5：缓存：pip/pnpm 缓存加速后续运行（actions/cache 或 setup-python 内置缓存）。

### 2.2 非功能需求

- 稳定性：锁依赖版本（pyproject/package-lock 均已提交）。
- 可读：job/step 命名清晰，日志可定位失败步骤。
- 兼容：bash 语法（GitHub runner 为 Linux）。

## 3. 技术方案

- 目录：`.github/workflows/ci.yml`。
- 后端 job：

```yaml
backend:
  runs-on: ubuntu-latest
  defaults: { run: { working-directory: apps/backend } }
  steps:
    - uses: actions/checkout@v4
    - uses: actions/setup-python@v5
      with: { python-version: "3.12", cache: "pip" }
    - run: pip install -e ".[dev]"
    - run: ruff check src tests
    - run: pytest -q
```

- 前端 job：

```yaml
web:
  runs-on: ubuntu-latest
  defaults: { run: { working-directory: apps/web } }
  steps:
    - uses: actions/checkout@v4
    - uses: pnpm/action-setup@v4
    - uses: actions/setup-node@v4
      with: { node-version: "20", cache: "pnpm" }
    - run: pnpm install --frozen-lockfile
    - run: pnpm lint
    - run: pnpm test
    - run: pnpm build
```

## 4. 接口定义

- 无 HTTP API；CI 为仓库级基础设施。

## 5. 验收标准

- [ ] AC1：`.github/workflows/ci.yml` 存在且 YAML 合法。
- [ ] AC2：本地等效命令全部通过：后端 `pytest -q` + `ruff check`；前端 `pnpm lint` + `pnpm test` + `pnpm build`。
- [ ] AC3：GitHub Actions workflow 语法校验通过（可用 `actionlint` 或提交后 CI 自测）。
- [ ] AC4：push develop 后 GitHub Actions 运行 backend + web 两个 job 全绿。

## 6. 测试计划

- 语法：actionlint 或 npx yaml-lint。
- 等效：本地逐一跑 CI 中每条命令，全部通过。
- 集成：push 到 develop 后观察 GitHub Actions 运行结果。

## 7. 里程碑与估算

| 子任务 | 预估 |
|---|---|
| ci.yml 编写 | 15 分钟 |
| 本地等效验证 | 15 分钟 |
| push + 观察 CI | 20 分钟 |

## 8. 风险与对策

| 风险 | 对策 |
|---|---|
| CI 与本地环境差异（路径/依赖解析） | 本地逐条等价命令先行校验 |
| pnpm frozen-lockfile 失败 | 本地已提交 lockfile；CI 用 frozen 强制一致 |
| runner 无 .venv（显式 workdir） | defaults.working-directory 显式指定 |

## 9. 变更记录

| 日期 | 变更内容 | 理由 |
|---|---|---|
| 2026-08-20 | 初始定稿 | — |
