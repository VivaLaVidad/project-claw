"""
run_stack.py - Project Claw v14.3
工业级进程编排启动脚本

改进：
- 启动前自动清理占用端口
- 健康检查等待 signaling 就绪
- 自动重启崩溃子进程
- 详细启动/退出日志
"""
from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import requests

from config import settings

ROOT   = Path(__file__).resolve().parent
PYTHON = Path(sys.executable)

SERVICES: dict[str, list[str]] = {
    "signaling": [
        str(PYTHON), "-m", "uvicorn",
        "a2a_signaling_server:app",
        "--host", settings.SIGNALING_HOST,
        "--port", str(int(os.environ.get("PORT", settings.SIGNALING_PORT))),
    ],
    "siri": [
        str(PYTHON), "-m", "uvicorn",
        "cloud_server.api_server_pro:app",
        "--host", "0.0.0.0",
        "--port", "8010",
    ],
    "dashboard": [
        str(PYTHON), "-m", "streamlit", "run",
        str(ROOT / "god_mode_dashboard.py"),
        "--server.port", "8501",
        "--server.headless", "true",
    ],
}

# 服务对应的端口（用于启动前清理）
_SERVICE_PORTS = {"signaling": 8765, "siri": 8010}


# ─── 工具函数 ─────────────────────────────────────────────────
def _log(msg: str) -> None:
    ts = time.strftime("%H:%M:%S")
    print(f"[stack {ts}] {msg}", flush=True)


def _kill_port(port: int) -> None:
    """强制释放端口，防止上次进程残留导致 bind 失败。"""
    try:
        result = subprocess.run(
            f"netstat -ano | findstr :{port} ",
            shell=True, capture_output=True, text=True,
        )
        for line in result.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 5 and "LISTENING" in parts:
                pid = parts[-1]
                subprocess.run(
                    f"taskkill /F /PID {pid}",
                    shell=True, capture_output=True,
                )
                _log(f"已释放端口 {port} (PID={pid})")
    except Exception:
        pass


def _wait_signaling_ready(timeout: int = 30) -> bool:
    """轮询等待 signaling 服务健康检查通过。"""
    url = f"{settings.signaling_http_base_url}/health"
    deadline = time.time() + timeout
    _log(f"等待 signaling 就绪: {url}")
    while time.time() < deadline:
        try:
            r = requests.get(url, timeout=2)
            if r.status_code < 400:
                _log("signaling 已就绪 ✓")
                return True
        except Exception:
            pass
        time.sleep(1)
    _log(f"signaling 在 {timeout}s 内未就绪，继续启动其他服务")
    return False


def start_service(name: str) -> subprocess.Popen:
    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")
    cmd = SERVICES[name]
    _log(f"启动 {name}: {' '.join(cmd)}")
    return subprocess.Popen(cmd, cwd=str(ROOT), env=env, text=True)


def terminate_all(processes: dict[str, subprocess.Popen]) -> None:
    for name, proc in processes.items():
        if proc.poll() is None:
            _log(f"停止 {name} (pid={proc.pid})")
            proc.terminate()
    deadline = time.time() + 8
    for proc in processes.values():
        if proc.poll() is None:
            try:
                proc.wait(timeout=max(0.1, deadline - time.time()))
            except subprocess.TimeoutExpired:
                proc.kill()


# ─── 主逻辑 ───────────────────────────────────────────────────
def main() -> int:
    parser = argparse.ArgumentParser(description="Project Claw 核心服务启动器")
    parser.add_argument(
        "services", nargs="*",
        choices=sorted(SERVICES.keys()),
        help="指定要启动的服务（默认: signaling siri）",
    )
    parser.add_argument("--no-restart", action="store_true", help="崩溃后不自动重启")
    args = parser.parse_args()

    selected = args.services or ["signaling", "siri"]
    processes: dict[str, subprocess.Popen] = {}

    def _shutdown(*_: object) -> None:
        _log("收到退出信号，正在停止所有服务...")
        terminate_all(processes)
        raise SystemExit(0)

    signal.signal(signal.SIGINT, _shutdown)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _shutdown)

    try:
        # ── 启动前清理占用端口 ──
        for svc in selected:
            port = _SERVICE_PORTS.get(svc)
            if port:
                _kill_port(port)
        time.sleep(1)  # 等待端口完全释放

        # ── 先启动 signaling ──
        if "signaling" in selected:
            processes["signaling"] = start_service("signaling")
            _wait_signaling_ready(timeout=30)

        # ── 再启动其余服务 ──
        for name in selected:
            if name == "signaling":
                continue
            processes[name] = start_service(name)

        _log(f"全部服务已启动: {list(processes.keys())}，按 Ctrl+C 停止")

        # ── 监控循环 ──
        while True:
            for name in list(processes.keys()):
                proc = processes[name]
                code = proc.poll()
                if code is not None:
                    _log(f"{name} 退出 (code={code})")
                    if args.no_restart:
                        terminate_all(processes)
                        return code
                    else:
                        port = _SERVICE_PORTS.get(name)
                        if port:
                            _kill_port(port)
                        _log(f"自动重启 {name}...")
                        time.sleep(2)
                        processes[name] = start_service(name)
            time.sleep(1)

    except KeyboardInterrupt:
        terminate_all(processes)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
