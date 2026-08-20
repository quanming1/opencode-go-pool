# 变更记录（CHANGELOG）

本项目按 Rondo 方法推进：阶段收尾三联动（PRD 已验收 + TODO done + CHANGELOG 追加）。

## [未发布]

### Added

- A1 仓库骨架 + Rondo 规范落地（AGENTS.md / TODO.yaml / PROCESS.md / PRD 模板 / githooks）
- A2 后端 FastAPI 骨架（应用工厂 / pydantic-settings 配置 / /health / pytest 5 passed）
- A3 前端 React+Vite+ECharts 骨架（白色简洁 UI 无阴影无圆角 / 示例折线图 / vitest 2 passed）
- B1 后端账号池：配置加载（YAML/JSON + env 引用）、账号状态机（healthy/cooldown/disabled + TTL 冷却）、GET /api/accounts 脱敏查询（pytest 27 passed）
- B2 后端透明转发：/api/v1/responses（选号-转发-非流式/SSE 流式透传）、错误分类（quota/auth/bad_request/server）与失败切换 mark_down、/api/v1/models、X-Pool-Account 追踪头（pytest 37 passed）
- B3 轮换强化：冷却主动扫描自动恢复、Retry-After 动态冷却、连续失败阈值自动禁用、切换历史环形日志（pytest 50 passed）
- B4 SQLite 状态持久化：account 运行时状态与切换历史落库、重启自动恢复（冷却/禁用/计数）、DB 不可写降级纯内存（pytest 61 passed）
- C1 前端账号状态大盘：账号卡片 + 状态徽章（健康/冷却/禁用）+ 统计摘要 + 10s 轮询；白色简洁风；删除 demo 占位（vitest 10 passed）
- C2 用量与轮换：后端 /api/stats（按小时桶/账号聚合）+ /api/switch-history（Thread 中文映射）+ 前端 ECharts 用量趋势图与轮换时间线（pytest 70 + vitest 13 passed）
- G1 CI：GitHub Actions workflow（backend pytest/ruff + web eslint/vitest/build），push/PR 自动校验
- G2 文档：根 README（架构/快速开始/API 汇总/配置表）+ 后端/前端 README + docs/usage.md 操作手册与 FAQ

### Fixed

- 账号密钥支持 apps/backend/.env.keys（KEY=VALUE）：${VAR} 解析顺序 = 进程环境变量 > .env.keys；密钥与应用配置（.env，严格模式）职责分离（B1 变更记录留痕）

### Added

- B2 扩展：POST /api/v1/chat/completions 透明转发（OpenCode 的 kimi/minimax/glm/deepseek 等 completions 模型；与 /responses 共用账号池与切换）
- 测试隔离：conftest fixture 用 tmp_path 隔离 config 与 DB，不再触碰本地真实账号配置与生产数据库
