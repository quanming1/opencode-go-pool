# PRD-G2-文档与示例

> 状态生命周期：草稿 → 评审 → approved（定稿）→ 开发中 → 已验收

## 元信息

| 字段 | 值 |
|---|---|
| 阶段 | G2 |
| 名称 | 文档与示例 |
| 状态 | 已验收 |
| 创建日期 | 2026-08-20 |
| 定稿日期 | 2026-08-20 |
| 验收日期 | 2026-08-20 |
| 关联文档 | docs/TODO.yaml 阶段 G2；全部前序 PRD（A1-C2/G1） |

## 1. 背景与目标

- **背景**：项目功能已齐（账号池/转发/轮换/持久化/大盘/CI），但文档只有骨架级 README——新读者无法从文档自助完成"从克隆到代理可用 + 大盘可视化"的完整路径。
- **目标**：根 README 成为从零启动到可用的一页指南（架构/启动/配置/API/curl 示例）；后端与前端 README 各自补齐子目录细节；文档与实际行为一致（以代码为准核对）。
- **非目标**：不做文档站/多语言；不做部署运维手册（Docker/K8s 后续）；不写 CHANGELOG 历史回填。

## 2. 需求范围

### 2.1 功能需求

- [ ] FR1：根 README.md 完善：项目定位、架构图（ASCII：ftre/客户端 → 代理 → 多 OpenCode 账号）、快速开始（后端+前端）、配置汇总（.env 全字段表）、API 汇总（端点/方法/说明/curl 示例）、目录结构、合规边界、Rondo 流程链接。
- [ ] FR2：后端 README（apps/backend/README.md）补齐：模块一览（accounts/proxy/usage/store/scheduler 职责表）、测试与 lint 命令、SQLite 数据说明（表/路径）。
- [ ] FR3：前端 README（apps/web/README.md）新建：技术栈、脚本命令、UI 规范（白色简洁/无阴影/无圆角）、目录结构。
- [ ] FR4：docs/usage.md 新建：面向使用者的操作手册——账号配置样例（env 引用）、启动顺序、验证步骤（/health、/api/accounts、/api/v1/responses curl 全流程）、大盘访问、常见问题（账号被自动禁用怎么办、DB 不可用降级说明）。
- [ ] FR5：文档中的所有命令与端口/路径与代码一致（48700 后端 / 48701 前端 / data/opencode_pool.db / config/accounts.yaml）。

### 2.2 非功能需求

- 准确性：以当前代码为唯一事实源核对每个端点/字段/命令。
- 简洁：README 一页可读，细节放 docs/usage.md。

## 3. 技术方案

- 修改/新增：README.md（根）、apps/backend/README.md、apps/web/README.md（新）、docs/usage.md（新）。
- API 汇总数据源：api/accounts.py、api/usage.py、proxy/router.py、app.py（/health）。

## 4. 接口定义

- 纯文档，无代码接口。

## 5. 验收标准

- [ ] AC1：四个文档文件存在且非模板占位。
- [ ] AC2：根 README 的快速开始命令逐条在本机可执行（后端启动/前端启动/curl 三连）。
- [ ] AC3：API 汇总覆盖全部 6 个端点（/health、/api/accounts、/api/stats、/api/switch-history、/api/v1/responses、/api/v1/models）且方法/说明正确。
- [ ] AC4：配置表覆盖 .env.example 全部字段。
- [ ] AC5：三联动（PRD 已验收 + TODO done + CHANGELOG）+ 全 PR 流合入。

## 6. 测试计划

- 手动核对：逐端点比对代码路由定义；逐命令执行。
- 读者视角走查：按文档从零操作一遍能否到达大盘可用。

## 7. 里程碑与估算

| 子任务 | 预估 |
|---|---|
| 根 README | 25 分钟 |
| 后端/前端 README | 20 分钟 |
| docs/usage.md | 25 分钟 |
| 核对验证 | 20 分钟 |

## 8. 风险与对策

| 风险 | 对策 |
|---|---|
| 文档与代码漂移 | 以路由代码逐一核对；验收含命令实跑 |
| 命令在不同 shell 失败 | 统一 bash/powershell 双写或注明 |

## 9. 变更记录

| 日期 | 变更内容 | 理由 |
|---|---|---|
| 2026-08-20 | 初始定稿 | — |
| 2026-08-20 | 验收通过：四文档齐备（根/后端/前端/usage），快速开始命令实测可跑，API 汇总覆盖全部 6 端点，配置表覆盖 .env 全字段 | 阶段 G2 完成 |
