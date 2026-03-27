from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from config import settings

ROOT = Path(__file__).resolve().parent
PYTHON = Path(sys.executable)

SERVICES = {
    "signaling": [
        str(PYTHON),
        "-m",
        "uvicorn",
        "a2a_signaling_server:app",
        "--host",
        settings.SIGNALING_HOST,
        "--port",
        str(settings.SIGNALING_PORT),
    ],
    "siri": [
        str(PYTHON),
        "-m",
        "uvicorn",
        "cloud_server.api_server_pro:app",
        "--host",
        settings.SIRI_HOST,
        "--port",
        str(settings.SIRI_PORT),
    ],
    "dashboard": [str(PYTHON), str(ROOT / "demo_dashboard.py")],
}


def start_service(name: str) -> subprocess.Popen[str]:
    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")
    print(f"[stack] starting {name}: {' '.join(SERVICES[name])}")
    return subprocess.Popen(
        SERVICES[name],
        cwd=str(ROOT),
        env=env,
        text=True,
    )


def terminate_processes(processes: dict[str, subprocess.Popen[str]]) -> None:
    for name, proc in processes.items():
        if proc.poll() is None:
            print(f"[stack] stopping {name} (pid={proc.pid})")
            proc.terminate()
    deadline = time.time() + 8
    for proc in processes.values():
        if proc.poll() is None:
            timeout = max(0.1, deadline - time.time())
            try:
                proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                proc.kill()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Project Claw core stack")
    parser.add_argument(
        "services",
        nargs="*",
        choices=sorted(SERVICES.keys()),
        help="Specific services to run. Defaults to signaling + siri.",
    )
    args = parser.parse_args()

    selected = args.services or ["signaling", "siri"]
    processes: dict[str, subprocess.Popen[str]] = {}

    def _shutdown(*_: object) -> None:
        terminate_processes(processes)
        raise SystemExit(0)

    signal.signal(signal.SIGINT, _shutdown)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _shutdown)

    try:
        for name in selected:
            processes[name] = start_service(name)
        print("[stack] services started, press Ctrl+C to stop")
        while True:
            for name, proc in processes.items():
                code = proc.poll()
                if code is not None:
                    print(f"[stack] {name} exited with code {code}")
                    terminate_processes(processes)
                    return code
            time.sleep(1)
    except KeyboardInterrupt:
        terminate_processes(processes)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
