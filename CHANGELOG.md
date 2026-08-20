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
