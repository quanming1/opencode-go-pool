# PRD-G4-代码优化·去除冗余代码

> 状态生命周期：草稿 → 评审 → approved（定稿）→ 开发中 → 已验收

## 元信息

| 字段 | 值 |
|---|---|
| 阶段 | G4 |
| 名称 | 代码优化 · 去除冗余代码 |
| 状态 | 开发中 |
| 创建日期 | 2026-08-21 |
| 定稿日期 | 2026-08-21 |
| 关联文档 | docs/TODO.yaml 阶段 G4；apps/backend/src/opencode_pool/accounts/pool.py；apps/backend/src/opencode_pool/store/sqlite_store.py；apps/backend/src/opencode_pool/logging_setup.py；apps/web/src/i18n/messages.ts；apps/web/src/index.css |

## 1. 背景与目标

- **背景**：迁移/演进过程中留存了少量**从未被调用的死代码**——项目 TS 侧因 `strict + noUnusedLocals + eslint` 已强制清过一轮，但**导出后无引用**的方法/模块与孤儿 i18n key / CSS 类不受其约束。逐文件扫描确认存在 5 处确凿死代码（含 1 处连带 import）。
- **目标**：清除全部已确认死代码，恢复"每段代码都有消费者"；以全量测试 + 复核扫描证明**零回归、零新增冗余**。
- **非目标**：不做行为重构（不改任何逻辑/样式效果）；不做大规模重写或抽取公共组件（超出"去冗余"范围）；不改第三方依赖与测试用例本身（除非被清项是它们唯一消费者）。

## 2. 扫描方法

用临时脚本对 `src/`（前端）与 `apps/backend`（后端）做三类静态扫描：
1. **无引用导出/方法**：提取命名导出（`export function/const`）与 `def`/方法名，统计在全库出现次数，仅定义处 1 次者列为候选；人工复核排除 pytest 用例、FastAPI 路由 handler（由框架收集，非死代码）。
2. **孤儿模块**：统计每个文件被其它文件 `import ... from` 的相对引用次数，0 次且非测试为候选。
3. **孤儿 i18n key / CSS 类**：messages.ts 的 `"key":` 全 src 无引用；CSS 类在 tsx `className` 无字符串命中（并对 `${...}` 模板拼接做人工复核，避免误报）。

## 3. 需求范围（清理清单与依据）

| # | 位置 | 内容 | 删除依据 |
|---|---|---|---|
| 1 | `accounts/pool.py:353-360` | `describe_key` 方法与「日志用脱敏」注释块 | 全库无调用（仅定义处 1 次）；其唯一消费方已改为统一事件脱敏 |
| 2 | `accounts/pool.py:22` | import 里的 `mask_api_key` | 删除 #1 后该 import 成为未使用（F401），连带移除 |
| 3 | `store/sqlite_store.py:612-626` | `has_any_gateway_key` 方法 | 全库无调用（鉴权启用判定已改用 `KeyManager`/`count` 路径） |
| 4 | `logging_setup.py`（整个文件） | `setup_logging` 与模块 | 全库无 `import logging_setup` / `setup_logging` 调用，整文件无消费者 |
| 5 | `i18n/messages.ts:86,249` | `chart.tooltip.success`（zh/en 各 1 key） | 全 src 无 `t("chart.tooltip.success")` 引用（E4 遗留孤儿 key） |
| 6 | `index.css:105-` | `.card-text` 规则 | tsx 无 `card-text` className 引用 |

**明确不做**：`list_accounts / disable_account / enable_account / responses_alias / chat_completions_alias / models_alias` 等 FastAPI 路由 handler（框架运行时引用，属活代码）；测试文件与 `test/setup.ts`（vitest 收集）；CSS 中 `--${x}`/`${x}` 模板拼接类（实际使用中）。

## 4. 接口定义

- 无 HTTP API 变更；无导出签名变更（删除项均无外部消费者）。

## 5. 验收标准

- [ ] AC1：5 处死代码 + 连带 import 全部移除（#1-#6 清单逐一核对：grep 不再命中）。
- [ ] AC2：后端 `pytest` 全绿（删除项无测试依赖：`describe_key`/`has_any_gateway_key`/`setup_logging` 有断言则先移除对应用例）、`ruff check src tests` 0 告警。
- [ ] AC3：前端 i18n zh/en key 集合一致（现有 `i18n.test.ts` 断言通过）；`vitest` 全绿；`eslint` 0；`pnpm build` 通过。
- [ ] AC4：复核扫描（复用摸底脚本）确认清理项全部消失、无新孤儿导出/模块/key/类。
- [ ] AC5：浏览器（playwright）抽查监控台正常渲染（无 404 模块、无样式回归）；三联动（PRD 已验收 + TODO G4 done + CHANGELOG）且 CI 三 job 绿。

## 6. 测试计划

- 删除前：确认目标无测试引用（`grep` 复核）。
- 删除后：后端 `pytest -p no:cacheprovider` + `ruff`；前端 `vitest run` + `eslint` + `build`。
- 复核：重跑三个扫描脚本，输出为空（除 pytest/vitest 手动排除项）。

## 7. 里程碑与估算

| 子任务 | 预估 |
|---|---|
| 后端 3+1 处清理 + 全量验证 | 20 分钟 |
| 前端 2 处清理 + 全量验证 | 15 分钟 |
| 复核扫描 + playwright 抽查 | 15 分钟 |
| 三联动 + CHANGELOG | 10 分钟 |

## 8. 风险与对策

| 风险 | 对策 |
|---|---|
| 删掉被框架收集的路由/测试 | 扫描对 pytest 用例、FastAPI handler、vitest 文件手动排除并复核 |
| 删除后 import 变未使用 | #2 连带处理；ruff F401 兜底 |
| CSS 类被模板拼接引用误删 | 对 `${...}` 形式人工核对；AC4 复核 |
| 孤儿 key 删除致 i18n 键集合不一致 | zh/en 同时删，i18n.test 断言兜底 |

## 9. 变更记录

| 日期 | 变更内容 | 理由 |
|---|---|---|
| 2026-08-21 | 初始定稿 | — |
| 2026-08-21 | 实现完成：后端 pool.py 删 describe_key 与「日志用脱敏」注释块、import 移除 mask_api_key；sqlite_store.py 删 has_any_gateway_key；删除 logging_setup.py 模块（setup_logging 无消费者）。前端 messages.ts 删 chart.tooltip.success（zh/en，E4 孤儿 key）；index.css 删 .card-text 死类 | 阶段 G4 开发 |
