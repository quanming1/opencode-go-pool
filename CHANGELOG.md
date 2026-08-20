# 变更记录（CHANGELOG）

本项目按 Rondo 方法推进：阶段收尾三联动（PRD 已验收 + TODO done + CHANGELOG 追加）。

## [0.3.0] - 2026-08-20

### Added

- D1 日志系统升级：请求日志记录模型与双协议 token（Chat Completions `prompt_tokens`/`completion_tokens` 与 Responses `input_tokens`/`output_tokens` 各自字段名，显式双协议用例锁定）；`/api/stats` 新增按账号×模型聚合（`per_account_models`，某 Key 收到多少次请求、分别什么模型与 token/错误）；`/api/logs/overview` 运行时概览（当前活跃 Key = 最近成功请求账号、近 60 分钟请求/token 速率、按滚动额度百分比+本地速率推算的剩余时长）；`/api/events` 支持 `offset` 分页（返回 has_more）；前端事件时间线自包含分页（20 条/页 + 字段详情展开 + 首帧自动刷新）、新增运行概览卡与「模型请求分布」「账号负载」两张 ECharts 图（pytest 135 + vitest 33 passed；独立端口端到端实测通过，全程未重启运行中的网关）

### Changed

- 优化用量信息摘要区：将账号状态与额度总览合并为单一面板，状态统计与额度信息同区展示；额度总览使用滚动/每周/每月三条总额度进度条。
- 开源准备：仓库公开（PUBLIC）、英文 README（中文迁移 README.zh-CN.md）、MIT License、SECURITY/CONTRIBUTING、安全审查报告（已追踪文件 + 全历史 blob + 已知 key 指纹 0 泄露、.gitignore 收窄 logs/ 为根目录避免误伤 Python 包）。

## [0.2.0] - 2026-08-20

首个可发布版本：OpenCode Go 多账号合并代理（账号池轮换 + 透明转发 + 持久化）+ React 监控台（大盘 / 用量 / 额度 / 事件）+ CI + 文档。

### Added

- A1 仓库骨架 + Rondo 规范落地（AGENTS.md / TODO.yaml / PROCESS.md / PRD 模板 / githooks）
- A2 后端 FastAPI 骨架（应用工厂 / pydantic-settings 配置 / /health / pytest 5 passed）
- A3 前端 React+Vite+ECharts 骨架（白色简洁 UI 无阴影无圆角 / vitest 2 passed）
- B1 后端账号池：配置加载（YAML/JSON + env 引用）、账号状态机（healthy/cooldown/disabled + TTL 冷却）、GET /api/accounts 脱敏查询（pytest 27 passed）
- B2 后端透明转发：/api/v1/responses（选号-转发-非流式/SSE 流式透传）、错误分类（quota/auth/bad_request/server）与失败切换 mark_down、/api/v1/models、X-Pool-Account 追踪头（pytest 37 passed）
- B2 扩展：POST /api/v1/chat/completions 透明转发（OpenCode 的 kimi/minimax/glm/deepseek 等 completions 模型；与 /responses 共用账号池与切换）+/v1/* 标准 OpenAI SDK 路径别名（LangChain 兼容，端到端实测通过）
- B3 轮换强化：冷却主动扫描自动恢复、Retry-After 动态冷却、连续失败阈值自动禁用、切换历史环形日志（pytest 50 passed）
- B4 SQLite 状态持久化：account 运行时状态与切换历史落库、重启自动恢复（冷却/禁用/计数）、DB 不可写降级纯内存（pytest 61 passed）
- C1 前端账号状态大盘：账号卡片 + 状态徽章（健康/冷却/禁用）+ 统计摘要 + 10s 轮询；删除 demo 占位（vitest 10 passed）
- C2 用量与轮换：后端 /api/stats（按小时桶/账号聚合）+ 前端 ECharts 用量趋势图（pytest 70 + vitest 13 passed）
- C3 分 Tab 管理与网关鉴权：左右分栏（用量信息/API Key 管理）；账号控制按钮（清除冷却/启用/禁用）；网关 key 生成/吊销 + 转发端点 Bearer 鉴权（本地默认免鉴权，GATEWAY_AUTH=on 启用）（pytest 84 + vitest 17 passed）
- C4 统一事件日志：所有事件统一 type/data/meta/time 契约（request 含 request_id/attempts 链/token/耗时、key_cooldown_started/completed、key_switch、all_keys_invalid/unavailable、key_disabled/enabled/cooldown_cleared、gateway_key_created/revoked 共 11 类）；SQLite events 表（保留 5000 条）启动自动迁移旧 switch_history 后删除；GET /api/events?type 筛选；前端事件时间线（pytest 105 + vitest 21 passed）
- C5 账号额度展示：基于官方 `/zen/go/v1/usage` 的每账号滚动/每周/每月用量与重置倒计时；服务端 60s TTL 缓存（Lock 防击穿）、单账号失败降级、?refresh=1 强制刷新；额度总览卡展示多账号总分配额度（$12/$30/$60 × N）与按百分比折算的估算已用美元；配置 QUOTA_CACHE_TTL_SECONDS / QUOTA_TIMEOUT_SECONDS（pytest 123 + vitest 31 passed；真实 6 账号接口与 UI 实测通过）
- G1 CI：GitHub Actions workflow（backend pytest/ruff + web eslint/vitest/build），push/PR 自动校验
- G2 文档：根 README（架构/快速开始/API 汇总/配置表）+ 后端/前端 README + docs/usage.md 操作手册与 FAQ
- 测试隔离：conftest fixture 用 tmp_path 隔离 config 与 DB，不触碰本地真实账号配置与生产数据库
- start.py 一键启动脚本：清理 48700/48701 端口占用（含 uvicorn --reload 孤儿子进程的双保险清理：按端口杀树 + 按命令行兜底）→ 静默（detached）启动前后端 → 健康检查；日志写 logs/（幂等，重复运行即重启）

### Fixed

- 账号密钥支持 apps/backend/.env.keys（KEY=VALUE）：${VAR} 解析顺序 = 进程环境变量 > .env.keys；密钥与应用配置（.env，严格模式）职责分离（B1 变更记录留痕）

## [未发布]

### Added

- G3 CICD 自动打包验证：ci.yml 扩展为 backend/web/pack 三 job 依赖链——backend 构建 wheel、web 构建 dist 并上传 artifact；pack job 用新增 `scripts/package_release.py`（纯标准库，本地可跑）把后端 wheel + 前端 dist + start.py/文档/示例配置组装成 `opencode-go-pool-<version>.zip`，并做真实校验（全新临时 venv 安装 wheel + import 版本断言、dist/index.html 引用的 /assets 资源全在包内、根文件清单断言）；产物上传 artifact `release-package`，推 `v*` tag 自动挂到对应 GitHub Release。pyproject dev 依赖补 build 包；README/README.zh-CN/CONTRIBUTING 同步（PR #82 合并，CI 三 job 全绿）
- E2 中英文切换 + 主题切换：自研轻量 i18n（zh/en 字典 + I18nProvider/useI18n，localStorage 持久化，未新增依赖）；CSS 变量双主题（:root 浅色 + `html[data-theme="dark"]` 深色，全站含 ECharts 动态取色）；header 语言/主题切换控件；13 个组件文案全部 t() 化、字典 key 一致性单测（vitest 34→38、eslint 0、build 通过；playwright 实测切 EN/Dark 即时生效且刷新持久化、无首帧闪烁）
- E1 响应式开发：建立 1024/768/576 断点体系（收敛旧 900/720）；窄屏（≤576）侧栏折叠为顶部 tab、内容区占满全宽；账号卡/概览/额度均值网格列改 `minmax(0,1fr)` 防内容撑破；keys 表格窄屏容器横滚；事件时间线小屏可换行；账号卡头部文本省略保护。playwright 实测 360/480/768/1024/1440 五视口无横向溢出（vitest 34 + eslint 0 + build 通过）

### Changed

- 优化用量信息摘要区：将账号状态与额度总览合并为单一面板，状态统计与额度信息同区展示；额度总览使用滚动/每周/每月三条总额度进度条。
- 开源准备：仓库公开（PUBLIC）、英文 README（中文迁移 README.zh-CN.md）、MIT License、SECURITY/CONTRIBUTING、安全审查报告（已追踪文件 + 全历史 blob + 已知 key 指纹 0 泄露、.gitignore 收窄 logs/ 为根目录避免误伤 Python 包）。
