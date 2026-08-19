# OpenCode Go Pool

多个 OpenCode Go 订阅账号合并为一个逻辑上游的代理服务 + 可视化监控台。

## 是什么

- 解决单个 OpenCode Go 账号 5 小时窗口限制不够用的问题：多账号组成池子，某个账号额度耗尽后自动切换到下一个。
- `apps/backend`：Python 3.12 + FastAPI——账号池管理、Responses 协议透明转发、额度错误识别与切换、状态持久化。
- `apps/web`：React + Vite + TypeScript + ECharts——账号状态大盘、用量趋势、轮换事件时间线。UI 白色简洁风（无阴影、无圆角）。

## 目录结构

```
opencode-go-pool/
├─ apps/
│  ├─ backend/     FastAPI 代理核心
│  └─ web/         React 监控台
├─ docs/           TODO.yaml / PROCESS.md / prd/
└─ .githooks/      提交与推送校验（本地强制）
```

## 快速开始

见各子目录 README（后端 / 前端）与 `docs/` 文档。

## 规范

本项目按 Rondo 方法推进（PRD 驱动 + 全 PR 流）：

- 行为规范：`AGENTS.md`
- 任务清单（唯一执行依据）：`docs/TODO.yaml`
- 推进办法（六步闭环）：`docs/PROCESS.md`
- 阶段 PRD：`docs/prd/`
- 提交与 push 校验：`.githooks/`（clone 后执行 `git config core.hooksPath .githooks`）

## 合规边界

只支持官方 API Key 的合法接入与故障切换；不实现 Cookie 抓取、Session 复用、凭证伪造等行为。多账号订阅是否允许集中到内部网关，请以 OpenCode 官方答复为准。
