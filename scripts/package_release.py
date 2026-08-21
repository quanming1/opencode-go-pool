"""生成并校验 opencode-go-pool 完整发布包（纯标准库，CI 与本地复用同一逻辑）。

用法：
    python scripts/package_release.py \\
        --out release --root . \\
        --backend-dist _artifacts/backend-dist \\
        --web-dist _artifacts/web-dist [--smoke-install]

行为：
1. 从 apps/backend/src/opencode_pool/__init__.py 解析 __version__（唯一版本事实源）；
2. 组装 opencode-go-pool-<ver>.zip（内部顶层统一 opencode-go-pool-<ver>/）：
   后端 wheel + 前端 dist + 根启动/说明/许可文件 + 示例配置 + docs/；
3. 结构校验：wheel 存在且版本匹配、dist/index.html 存在且其引用的
   /assets/*.js|css 资源齐全、根文件清单/示例配置/docs 存在；
4. 可选 --smoke-install：在全新临时 venv 中 pip install zip 内 wheel 并
   import opencode_pool 断言版本（验证产物不仅结构对、真能装）；
5. 打印报告；任一校验失败退出码非 0（供 CI 判定）。

跨平台：仅使用标准库（zipfile/pathlib/re/venv/subprocess），Linux/Windows 均可跑。
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

WHEEL_TOP = "apps/backend/wheels"
WEB_DIST_TOP = "apps/web/dist"
# 发布包必须包含的根文件（缺一即校验失败）
ROOT_FILES = [
    "start.py",
    "README.md",
    "README.zh-CN.md",
    "LICENSE",
    "SECURITY.md",
    "CONTRIBUTING.md",
    "CHANGELOG.md",
]
# 部署必需但源码里被 gitignore 的示例配置，随包发布
EXAMPLE_FILES = [
    "apps/backend/.env.example",
    "apps/backend/config/accounts.example.yaml",
]
DOC_DIRS = ["docs"]


class PackagingError(Exception):
    """校验/组装失败，统一捕获为非 0 退出。"""


def read_version(root: Path) -> str:
    init_py = root / "apps/backend/src/opencode_pool/__init__.py"
    if not init_py.is_file():
        raise PackagingError(f"未找到版本文件：{init_py}")
    m = re.search(r'__version__\s*=\s*"([^"]+)"', init_py.read_text(encoding="utf-8"))
    if not m:
        raise PackagingError(f"无法解析 __version__：{init_py}")
    return m.group(1)


def list_wheels(dir_path: Path) -> list[Path]:
    if not dir_path.is_dir():
        raise PackagingError(f"后端构建目录不存在：{dir_path}")
    wheels = sorted(dir_path.glob("*.whl"))
    if not wheels:
        raise PackagingError(
            f"后端构建目录 {dir_path} 内未找到 *.whl（请先 `python -m build`）"
        )
    return wheels


def web_index(dist: Path) -> Path:
    index = dist / "index.html"
    if not index.is_file():
        raise PackagingError(f"前端产物缺少 dist/index.html：{dist}")
    return index


def asset_paths(index_html: str) -> list[str]:
    """从 index.html 提取引用的 /assets/ 静态资源名（src/href）。"""
    assets: list[str] = []
    # <script src="/assets/index-xxx.js" crossorigin></script>
    # <link rel="stylesheet" href="/assets/index-xxx.css" />
    for m in re.finditer(r'(?:src|href)="(/assets/[^"]+\.(?:js|css))"', index_html):
        path = m.group(1)
        if path not in assets:
            assets.append(path)
    return assets


def verify_web_assets(index: Path, dist: Path) -> list[str]:
    """校验 index.html 引用资源 /assets/* 都能在 dist 内找到，返回缺失列表。"""
    text = index.read_text(encoding="utf-8")
    missing: list[str] = []
    for rel in asset_paths(text):
        # 去掉前导 / 得到相对 dist 的路径
        candidate = dist / (rel.lstrip("/"))
        if not candidate.is_file():
            missing.append(rel)
    return missing


def archive_file(zf: zipfile.ZipFile, top: str, src: Path, rel_in_arc: str) -> None:
    zf.write(src, f"{top}/{rel_in_arc}")


def archive_dir(zf: zipfile.ZipFile, top: str, src_dir: Path, arc_dir: str) -> int:
    """递归写目录，返回写入条目数（跳过 __pycache__、.venv）。"""
    count = 0
    for p in sorted(src_dir.rglob("*")):
        if not p.is_file():
            continue
        parts = p.relative_to(src_dir).parts
        if "__pycache__" in parts or ".venv" in parts:
            continue
        target = f"{top}/{arc_dir}/{p.relative_to(src_dir).as_posix()}"
        zf.write(p, target)
        count += 1
    return count


def build_zip(
    out_dir: Path,
    root: Path,
    backend_dist: Path,
    web_dist: Path,
    version: str,
) -> Path:
    """组装发布 zip 并做结构校验；返回 zip 路径。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    zip_path = out_dir / f"opencode-go-pool-{version}.zip"
    top = f"opencode-go-pool-{version}"
    wheels = list_wheels(backend_dist)
    index = web_index(web_dist)

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # 1) 后端 wheel（全部 *.whl，通常 1 个）
        for wheel in wheels:
            zf.write(wheel, f"{top}/{WHEEL_TOP}/{wheel.name}")
            if version and version not in wheel.name:
                print(f"  [警告] wheel 名不含版本 {version}：{wheel.name}")
        # 2) 前端 dist 全量（保留资源相对结构）
        archive_dir(zf, top, web_dist, WEB_DIST_TOP)
        # 3) 根文件
        for rel in ROOT_FILES:
            src = root / rel
            if not src.is_file():
                raise PackagingError(f"根文件缺失：{rel}（在 {root}）")
            archive_file(zf, top, src, rel)
        # 4) 示例配置
        for rel in EXAMPLE_FILES:
            src = root / rel
            if not src.is_file():
                raise PackagingError(f"示例配置缺失：{rel}（在 {root}）")
            archive_file(zf, top, src, rel)
        # 5) docs/（TODO.yaml / PROCESS.md / prd/*）
        for doc in DOC_DIRS:
            src_dir = root / doc
            if not src_dir.is_dir():
                raise PackagingError(f"docs 目录缺失：{src_dir}")
            archive_dir(zf, top, src_dir, doc)

    # ---- 结构校验（独立于组装，逐条断言，失败抛 PackagingError）----
    with zipfile.ZipFile(zip_path) as zf:
        names = set(zf.namelist())
        missing_files = [
            f"{top}/{rel}" for rel in ROOT_FILES if f"{top}/{rel}" not in names
        ]
        if missing_files:
            raise PackagingError(f"zip 缺少根文件：{missing_files}")
        for rel in EXAMPLE_FILES:
            if f"{top}/{rel}" not in names:
                raise PackagingError(f"zip 缺少示例配置：{rel}")
        if f"{top}/{WEB_DIST_TOP}/index.html" not in names:
            raise PackagingError("zip 缺少 dist/index.html")
        inside = zf.read(f"{top}/{WEB_DIST_TOP}/index.html").decode("utf-8")
        inside_missing = []
        for rel in asset_paths(inside):
            key = f"{top}/{WEB_DIST_TOP}{rel}"
            if key not in names:
                inside_missing.append(rel)
        if inside_missing:
            raise PackagingError(f"dist/index.html 引用的资源在 zip 内缺失：{inside_missing}")
        if not any(n.startswith(f"{top}/{WHEEL_TOP}/") and n.endswith(".whl") for n in names):
            raise PackagingError(f"zip 内缺少 wheel（{top}/{WHEEL_TOP}/*.whl）")
        if not any(n.startswith(f"{top}/docs/") for n in names):
            raise PackagingError("zip 内缺少 docs/")

    return zip_path


def smoke_install(zip_path: Path, version: str) -> None:
    """在全新临时 venv 安装 zip 内 wheel 并断言版本，验证产物可安装。"""
    with tempfile.TemporaryDirectory(prefix="ocp-pack-") as tmp:
        tmp_dir = Path(tmp)
        wheels_dir = tmp_dir / "wheels"
        wheels_dir.mkdir()
        with zipfile.ZipFile(zip_path) as zf:
            top = zf.namelist()[0].split("/", 1)[0]
            for info in zf.infolist():
                if info.filename.startswith(f"{top}/{WHEEL_TOP}/") and info.filename.endswith(".whl"):
                    zf.extract(info, wheels_dir)
        wheel = next(wheels_dir.rglob("*.whl"))
        venv_dir = tmp_dir / "venv"
        subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True)
        py = venv_dir / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
        subprocess.run([str(py), "-m", "pip", "install", "--quiet", str(wheel)], check=True)
        check_code = (
            "import opencode_pool, importlib.metadata as m; "
            "assert opencode_pool.__version__ == %r, (opencode_pool.__version__, %r); "
            "print('installed', opencode_pool.__version__)"
            % (version, version)
        )
        subprocess.run([str(py), "-c", check_code], check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="组装并校验 opencode-go-pool 发布包")
    parser.add_argument("--out", default="release", help="输出目录（zip 生成位置）")
    parser.add_argument("--root", default=".", help="仓库根目录")
    parser.add_argument("--backend-dist", required=True, help="后端构建产物目录（含 *.whl）")
    parser.add_argument("--web-dist", required=True, help="前端 dist 目录")
    parser.add_argument(
        "--smoke-install", action="store_true", help="额外做 wheel 真实安装冒烟验证"
    )
    args = parser.parse_args()

    try:
        root = Path(args.root).resolve()
        version = read_version(root)
        print(f"[1/3] 版本来源：{version}")
        zip_path = build_zip(
            Path(args.out), root, Path(args.backend_dist), Path(args.web_dist), version
        )
        count = sum(1 for _ in zipfile.ZipFile(zip_path).namelist())
        size_kb = zip_path.stat().st_size // 1024
        print(f"[2/3] 组装完成：{zip_path}（{count} 个文件，{size_kb} KB）")
        if args.smoke_install:
            print("[3/3] wheel 安装冒烟...")
            smoke_install(zip_path, version)
            print("      冒烟通过：临时 venv 安装成功并 import 版本一致")
    except (PackagingError, subprocess.CalledProcessError) as exc:
        print(f"[失败] {exc}", file=sys.stderr)
        return 1
    print("校验通过：结构完整、产物可用")
    return 0


if __name__ == "__main__":
    sys.exit(main())
