"""一键重启 opencode-go-pool 前后端（Windows 开发环境）。

用法：
    python start.py

行为：
1. 清理 48700（后端）/ 48701（前端）端口占用：
   - 按 LISTENING 端口找到 PID，taskkill /T /F 杀整棵进程树；
   - 兜底按命令行匹配本项目残留进程再杀一轮——uvicorn --reload 的 worker 是
     multiprocessing 孤儿子进程，父进程死后 socket 表项仍指向死 PID，仅按端口杀不掉。
2. 等待端口释放（仍被占则报错退出，避免 vite 自动换端口造成"看起来启动了"的假象）。
3. 静默（detached，无窗口）启动后端 uvicorn(48700, --reload) 与前端 vite(48701)；
   日志分别追加写 logs/backend.log、logs/web.log。
4. 健康检查通过后脚本退出，服务在后台常驻。

依赖：仅 Python 标准库 + apps/backend/.venv + pnpm（PATH 可见）。
"""

import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND_DIR = ROOT / "apps" / "backend"
WEB_DIR = ROOT / "apps" / "web"
LOG_DIR = ROOT / "logs"

BACKEND_PORT = 48700
WEB_PORT = 48701

# detached 启动：新进程脱离当前控制台独立存活（脚本退出/关终端都不影响服务）
DETACHED_FLAGS = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP

BACKEND_START_TIMEOUT = 45.0
WEB_START_TIMEOUT = 45.0


# ---- 端口与进程清理 ----

def listening_pids(port: int) -> set[int]:
    """返回 LISTENING 在 port 上的 PID 集合（解析 netstat -ano）。"""
    out = subprocess.run(
        ["netstat", "-ano"], capture_output=True, text=True
    ).stdout
    pids: set[int] = set()
    for line in out.splitlines():
        parts = line.split()
        # 列格式: Proto Local Foreign State PID；Local 形如 127.0.0.1:48700 / [::1]:48701
        if len(parts) >= 5 and parts[3] == "LISTENING" and parts[1].endswith(f":{port}"):
            pids.add(int(parts[4]))
    return pids


def kill_pids(pids) -> None:
    """taskkill /T /F 杀整棵进程树；PID 已死等失败静默忽略。"""
    for pid in pids:
        subprocess.run(
            ["taskkill", "/T", "/F", "/PID", str(pid)],
            capture_output=True, text=True,
        )


def kill_port_owners(ports) -> list[int]:
    """按端口杀进程树，返回实际发过 taskkill 的 PID。"""
    all_pids: set[int] = set()
    for port in ports:
        all_pids |= listening_pids(port)
    if all_pids:
        kill_pids(all_pids)
    return sorted(all_pids)


def kill_strays() -> list[int]:
    """按命令行兜底杀本项目残留进程（孤儿 worker 的端口表项指向死 PID 时靠这步）。

    匹配规则：命令行含本项目路径 opencode-go-pool 且含 uvicorn/vite/pnpm。
    关键词在 PowerShell 里拆分拼接，避免查询进程自身命令行命中规则把自己杀掉。
    """
    ps = (
        "$k1='uvi'+'corn'; $k2='vi'+'te'; $k3='p'+'npm'; $p='opencode'+'-go-pool'; "
        "Get-CimInstance Win32_Process | Where-Object { "
        "$_.CommandLine -match $p -and ($_.CommandLine -match $k1 "
        "-or $_.CommandLine -match $k2 -or $_.CommandLine -match $k3) "
        "} | Select-Object -ExpandProperty ProcessId"
    )
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps],
        capture_output=True, text=True,
    ).stdout
    pids = [int(x) for x in out.split() if x.isdigit()]
    if pids:
        kill_pids(pids)
    return pids


def wait_ports_free(ports, timeout: float = 10.0) -> bool:
    """等待全部端口无 LISTENING；超时返回 False。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if all(not listening_pids(p) for p in ports):
            return True
        time.sleep(0.5)
    return all(not listening_pids(p) for p in ports)


# ---- 静默启动 ----

def start_backend() -> None:
    py = BACKEND_DIR / ".venv" / "Scripts" / "python.exe"
    if not py.is_file():
        sys.exit(f"[错误] 未找到后端虚拟环境 Python：{py}\n       请先在 apps/backend 创建 .venv 并安装依赖")
    LOG_DIR.mkdir(exist_ok=True)
    # PYTHONUTF8=1：子进程日志统一 utf-8，避免 GBK 乱码
    env = {**os.environ, "PYTHONUTF8": "1"}
    with open(LOG_DIR / "backend.log", "ab") as log:
        subprocess.Popen(
            [
                str(py), "-m", "uvicorn", "opencode_pool.app:app",
                "--host", "127.0.0.1", "--port", str(BACKEND_PORT), "--reload",
            ],
            cwd=str(BACKEND_DIR),
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            creationflags=DETACHED_FLAGS,
            env=env,
            close_fds=True,
        )


def start_web() -> None:
    pnpm = shutil.which("pnpm")
    if pnpm is None:
        sys.exit("[错误] 未找到 pnpm（请先安装并加入 PATH）")
    LOG_DIR.mkdir(exist_ok=True)
    with open(LOG_DIR / "web.log", "ab") as log:
        subprocess.Popen(
            [pnpm, "dev"],
            cwd=str(WEB_DIR),
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            creationflags=DETACHED_FLAGS,
            close_fds=True,
        )


# ---- 健康检查 ----

def http_ok(url: str, timeout: float = 2.0) -> bool:
    """GET 200 判定；显式空代理（本机服务不走系统代理，避免 Clash 拦截 localhost）。"""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(url, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


def tcp_up(host: str, port: int, timeout: float = 2.0) -> bool:
    """TCP 可连即视为端口服务在线（vite 监听 [::1]，socket 会遍历地址族）。"""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def wait_until(check, timeout: float, interval: float = 0.5) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if check():
            return True
        time.sleep(interval)
    return check()


def log_tail(name: str, lines: int = 12) -> str:
    path = LOG_DIR / name
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        return "\n".join(text.splitlines()[-lines:])
    except OSError:
        return "(暂无日志)"


# ---- 主流程 ----

def main() -> int:
    if os.name != "nt":
        sys.exit("[错误] 本脚本仅支持 Windows（taskkill/netstat 依赖）")

    print("[1/4] 清理端口占用（48700 后端 / 48701 前端）...")
    killed_ports = kill_port_owners([BACKEND_PORT, WEB_PORT])
    killed_strays = kill_strays()
    if killed_ports or killed_strays:
        print(f"      已终止：端口 PID {killed_ports or '无'}；残留匹配 {killed_strays or '无'}")
    else:
        print("      端口空闲，无需清理")

    print("[2/4] 等待端口释放...")
    if not wait_ports_free([BACKEND_PORT, WEB_PORT]):
        busy = [p for p in (BACKEND_PORT, WEB_PORT) if listening_pids(p)]
        sys.exit(f"[错误] 端口 {busy} 仍被占用，请手动检查后重试")
    print("      端口已释放")

    print("[3/4] 静默启动前后端...")
    start_backend()
    start_web()

    print("[4/4] 健康检查...")
    if not wait_until(lambda: http_ok(f"http://127.0.0.1:{BACKEND_PORT}/health"),
                      BACKEND_START_TIMEOUT):
        print("[错误] 后端未在时限内就绪，最近日志（logs/backend.log）：")
        print(log_tail("backend.log"))
        return 1
    print(f"      后端 ok  http://127.0.0.1:{BACKEND_PORT}/health")

    if not wait_until(lambda: tcp_up("localhost", WEB_PORT), WEB_START_TIMEOUT):
        print("[错误] 前端未在时限内就绪，最近日志（logs/web.log）：")
        print(log_tail("web.log"))
        return 1
    print(f"      前端 ok  http://localhost:{WEB_PORT}")

    print()
    print("启动完成（服务在后台常驻，日志见 logs/）：")
    print(f"  监控台    http://localhost:{WEB_PORT}")
    print(f"  后端 API  http://127.0.0.1:{BACKEND_PORT}")
    print("  再次运行本脚本 = 重启（先清理旧进程再启动）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
