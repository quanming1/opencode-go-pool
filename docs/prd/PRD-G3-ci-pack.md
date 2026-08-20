# PRD-G3-CICD自动打包验证

> 状态生命周期：草稿 → 评审 → approved（定稿）→ 开发中 → 已验收

## 元信息

| 字段 | 值 |
|---|---|
| 阶段 | G3 |
| 名称 | CICD 自动打包验证 |
| 状态 | 开发中 |
| 创建日期 | 2026-08-20 |
| 定稿日期 | 2026-08-20 |
| 关联文档 | docs/TODO.yaml 阶段 G3；.github/workflows/ci.yml；scripts/package_release.py |

## 1. 背景与目标

- **背景**：现有 CI（G1 阶段 `ci.yml`）只在 prune 时跑测试到"绿"为止，从不产出可分发产物——后端 wheel、前端 dist 均不构建/上传；发布依赖本地手动 build，未经机器验证，易漏示例配置（`.env.example`、`accounts.example.yaml`）、易混淆版本号。
- **目标**：GitHub Actions 在每次 push/PR 自动完成「测试 → 构建后端 wheel / 前端 dist → 组装完整发布包 → 真实产物验证 → 上传 artifact」；tag `v*` 推送时自动把发布包挂到 GitHub Release，实现"CI 绿 = 产物可用"。
- **非目标**：不做 Docker 镜像（当前无容器部署载体）；不做自动版本号 bump（版本冻结仍走 `release/<ver>` 分支 + tag）；不做 Windows/macOS 构建矩阵（沿用 linux runner，够用且省时）。

## 2. 需求范围

### 2.1 功能需求

- [ ] FR1：backend job 测试通过后构建 wheel/sdist（`python -m build`，hatchling）并上传 artifact（名 `backend-dist`）。
- [ ] FR2：web job 完成 `build` 后上传 `dist/` 目录为 artifact（名 `web-dist`）。
- [ ] FR3：新增 pack job（`needs: [backend, web]`）：checkout + 下载两 artifact，运行 `scripts/package_release.py` 组装 `opencode-go-pool-<version>.zip`（内部含后端 wheel、前端 dist、根启动/说明文件、示例配置、docs/），执行结构校验，上传最终 zip 为 artifact（名 `release-package`）。
- [ ] FR4：产物验证不造假——zip 内 wheel 在全新临时 venv `pip install` 后 `import opencode_pool` 并断言 `__version__`；`dist/index.html` 存在且其引用的 JS/CSS hash 资源均存在于 dist；根文件齐全按清单断言。
- [ ] FR5：tag `v*` 推送时，pack job 额外把 `release-package` 上传到对应 GitHub Release（用 gh CLI；Release 不存在则自动创建）。
- [ ] FR6：`scripts/package_release.py` 为**纯标准库**单文件（`zipfile`/`pathlib`/`re`/`argparse`），本地可直接运行，CI 与本地复用同一逻辑（交叉验证、可离线调试）。
- [ ] FR7：README（英文）+ README.zh-CN + CONTRIBUTING 同步 CICD 打包验证说明。

### 2.2 非功能需求

- 只读 CICD：不引入第三方 action（`actions/checkout`/`actions/upload-artifact`/`actions/download-artifact` 等官方 core action 除外）；Release 上传用 runner 自带 gh CLI。
- 跨平台：`package_release.py` 纯标准库，Linux/Windows 均可运行。
- 稳定：artifact 名固定、zip 文件名含版本号；校验失败即非 0 退出（CI 红）。

## 3. 技术方案

### 3.1 ci.yml 结构（三个 job 依赖链 backend/web → pack）

- 触发：`push`（branches: develop、main）+ `pull_request`（branches: develop、main）+ `push`（tags: `v*`）。
- 顶层 `permissions: contents: write`（Release 创建/上传需要，GITHUB_TOKEN 默认只读）。

```yaml
jobs:
  backend:
    # ...现有 pytest/ruff...
    - name: Build wheel
      run: pip install build && python -m build --outdir dist
    - name: Upload backend dist
      uses: actions/upload-artifact@v4
      with: { name: backend-dist, path: apps/backend/dist, ... }
  web:
    # ...现有 lint/test/build...
    - name: Upload web dist
      uses: actions/upload-artifact@v4
      with: { name: web-dist, path: apps/web/dist, ... }
  pack:
    needs: [backend, web]
    steps:
      - uses: actions/checkout@v4            # 取根文件（start.py/README/LICENSE/docs）
      - uses: actions/download-artifact@v4 { name: backend-dist, path: _artifacts/backend-dist }
      - uses: actions/download-artifact@v4 { name: web-dist,      path: _artifacts/web-dist }
      - run: python scripts/package_release.py --out release --root . \
             --backend-dist _artifacts/backend-dist --web-dist _artifacts/web-dist
      - uses: actions/upload-artifact@v4 { name: release-package, path: release/*.zip }
      - name: Upload to GitHub Release
        if: startsWith(github.ref, 'refs/tags/v')
        run: |  # gh CLI：先建后传
          VERSION="${GITHUB_REF_NAME#v}"
          gh release create "v${VERSION}" release/*.zip --title "v${VERSION}" --generate-notes || true
          gh release upload "v${VERSION}" release/*.zip --clobber
```

### 3.2 package_release.py CLI

```
python scripts/package_release.py \
    --out <dir>             # 输出目录（zip 生成位置）
    --root <repo-root>      # 仓库根（读 start.py/README/LICENSE/.../docs）
    --backend-dist <dir>    # 含 *.whl 的后端构建目录
    --web-dist <dir>        # 前端 dist 目录
```

行为：

1. 从 `apps/backend/src/opencode_pool/__init__.py` 正则解析 `__version__`（不硬编码）。
2. 组装 zip，顶层统一 `opencode-go-pool-<ver>/`，内部结构：

   ```
   opencode-go-pool-<ver>/
     apps/backend/wheels/opencode_pool-<ver>-*.whl     # 后端安装包
     apps/web/dist/...                                 # 前端构建产物（保留资源相对结构）
     start.py                                          # 一键启动脚本
     README.md / README.zh-CN.md / LICENSE / SECURITY.md / CONTRIBUTING.md / CHANGELOG.md
     apps/backend/.env.example                         # 示例配置（部署必需）
     apps/backend/config/accounts.example.yaml         # 示例账号配置
     docs/（TODO.yaml / PROCESS.md / prd/）
   ```

3. 结构校验（全部通过才写 zip / 返回 0）：
   - wheel 存在且版本号匹配；
   - `dist/index.html` 存在；
   - 解析 `index.html` 内 `src`/`href` 引用的 `/assets/*.js|css`，逐一存在于 dist；
   - 根文件清单（start.py、README.md、README.zh-CN.md、LICENSE、SECURITY.md、CONTRIBUTING.md、CHANGELOG.md）、示例配置、docs/ 存在。
4. 打印校验报告（文件数、字节数、版本）。

### 3.3 产物验证（CI 额外一步）

pack job 在生成 zip 后，做真实安装冒烟（不出包也能定位问题）：

```bash
python -m venv /tmp/verify && /tmp/verify/bin/pip install release/解出的 wheel
python -c "import opencode_pool; from opencode_pool.app import create_app; ...版本断言"
```

（此步骤在 pack job 中作为独立 step，脚本的 zip 内校验已保证结构；冒烟验证可安装性。）

## 4. 接口定义

- 无 HTTP API；CLI 见 3.2。
- 退出码：`0` 成功；非 `0` 校验失败/参数错误（供 CI 判定）。

## 5. 验收标准

- [ ] AC1：`ci.yml` 扩展为 backend/web/pack 三 job 依赖链，YAML 合法（actionlint 或 GitHub Actions 自测）。
- [ ] AC2：本地等效命令全部通过：后端 `pytest` + `ruff`（已有）+ `python -m build` 产出 wheel；前端 `lint` + `test` + `build`（已有）+ `dist/` 存在。
- [ ] AC3：`scripts/package_release.py --check`（或组装即校验）对**真实本地产物**跑通：生成 `opencode-go-pool-<ver>.zip`，结构校验通过（wheel 可安装 import、dist/index.html 及全部引用资源存在、根文件齐全）；失败路径退出码非 0。
- [ ] AC4：push feature 分支提 PR 后，GitHub Actions 跑 backend/web/pack 三 job 全绿，PR Checks 页可见 `release-package` artifact 可下载。
- [ ] AC5：README（英文）+ README.zh-CN + CONTRIBUTING 含 CICD 打包验证说明。
- [ ] AC6：临时推送一个测试 tag `v0.3.1`，release-package 自动上传到对应 GitHub Release asset；验证后删除测试 tag 与 release。

## 6. 测试计划

- 语法：GitHub Actions 自测（push 触发）+ 本地 YAML 检查。
- 脚本单测：`package_release.py` 对真实产物本地组装 + 校验 + 冒烟安装。
- 集成 CI：PR 触发三 job 全绿 + artifact 出现；tag 推送触发 Release 上传冒烟。

## 7. 里程碑与估算

| 子任务 | 预估 |
|---|---|
| ci.yml 扩展（三 job + tag release） | 20 分钟 |
| scripts/package_release.py 编写 | 40 分钟 |
| 本地验证（build/组装/校验/冒烟） | 20 分钟 |
| push + PR → CI 三 job 观察 | 20 分钟 |
| tag Release 冒烟 + 清理 | 15 分钟 |
| 文档同步（README/CONTRIBUTING） | 10 分钟 |

## 8. 风险与对策

| 风险 | 对策 |
|---|---|
| wheel 构建需要 build 包 | CI 中 `pip install build`（hatchling 已为 build-system） |
| 多 job 上传同名 artifact 被合并 | 使用唯一 artifact 名（backend-dist / web-dist / release-package） |
| tag 推送同时触发 PR/push 双运行 | release 上传用 `if: startsWith(github.ref, 'refs/tags/v')` 收敛，仅 pack job 内执行 |
| GITHUB_TOKEN 无 Release 写权限 | workflow 顶层声明 `permissions: contents: write`；gh CLI 用 `GH_TOKEN` 环境变量 |
| artifact 默认 90 天过期 | 本阶段够用；如需延长后续再配（非本阶段范围） |
| 版本号散落三处不一致 | zip 命名/校验统一读取 `__init__.py` 的 `__version__`（唯一事实源，发布时三处手改保持一致） |

## 9. 变更记录

| 日期 | 变更内容 | 理由 |
|---|---|---|
| 2026-08-20 | 初始定稿 | — |
| 2026-08-20 | 实现完成：ci.yml 扩展为 backend/web/pack 三 job（wheel/dist artifact + 组装校验 + tag 自动 Release）；新增 scripts/package_release.py（纯标准库）；pyproject dev 加 build 依赖；README/README.zh-CN/CONTRIBUTING 同步 | 阶段 G3 开发 |
