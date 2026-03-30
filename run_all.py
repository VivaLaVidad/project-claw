"""
Project Claw v14.0 - one-click launcher (industrial)

用途：统一拉起三端并做基础健康检查
  1) cloud_server (FastAPI + WebSocket hub)
  2) edge_box    (商家边缘盒子)
  3) mock_client (C端模拟器，可选)

示例：
  python run_all.py
  python run_all.py --skip-client
  python run_all.py --client-item 麻辣烫 --client-max 12
  python run_all.py --run-a2a-smoke
  python run_all.py --run-regression --regression-online
"""
from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import List, Optional

ROOT = Path(__file__).resolve().parent


class ProcGroup:
    def __init__(self):
        self._procs: List[subprocess.Popen] = []

    def add(self, p: subprocess.Popen):
        self._procs.append(p)

    def terminate_all(self):
        for p in reversed(self._procs):
            if p.poll() is not None:
                continue
            try:
                if os.name == "nt":
                    p.send_signal(signal.CTRL_BREAK_EVENT)
                    time.sleep(0.5)
                p.terminate()
            except Exception:
                pass

        deadline = time.time() + 8
        for p in self._procs:
            while p.poll() is None and time.time() < deadline:
                time.sleep(0.2)

        for p in self._procs:
            if p.poll() is None:
                try:
                    p.kill()
                except Exception:
                    pass


def _wait_health(url: str, timeout_sec: float = 30) -> bool:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                if 200 <= resp.status < 300:
                    return True
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
            pass
        time.sleep(0.5)
    return False


def _spawn(cmd: List[str], cwd: Optional[Path] = None) -> subprocess.Popen:
    kwargs = {
        "cwd": str(cwd) if cwd else None,
        "stdout": None,
        "stderr": None,
        "stdin": None,
    }
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    return subprocess.Popen(cmd, **kwargs)


def main():
    parser = argparse.ArgumentParser(description="Project Claw 一键拉起三端")
    parser.add_argument("--python", default=sys.executable, help="Python 解释器路径")
    parser.add_argument("--host", default="0.0.0.0", help="Hub 监听地址")
    parser.add_argument("--port", type=int, default=8765, help="Hub 监听端口")
    parser.add_argument("--skip-client", action="store_true", help="只启动云端+B端，不启动C端模拟器")
    parser.add_argument("--client-id", default="sim-client-001")
    parser.add_argument("--client-item", default="牛肉面")
    parser.add_argument("--client-max", type=float, default=15.0)
    parser.add_argument("--health-timeout", type=float, default=30.0)
    parser.add_argument("--run-a2a-smoke", action="store_true", help="启动后执行 A2A 冒烟测试")
    parser.add_argument("--run-regression", action="store_true", help="启动后执行模块回归测试套件")
    parser.add_argument("--regression-online", action="store_true", help="回归测试启用在线联调用例")
    parser.add_argument("--a2a-source", default="box-001")
    parser.add_argument("--a2a-targets", default="box-002,box-003,box-004")
    args = parser.parse_args()

    python_exe = args.python
    cloud_cmd = [
        python_exe,
        "-m",
        "uvicorn",
        "cloud_server.signaling_hub:app",
        "--host",
        args.host,
        "--port",
        str(args.port),
    ]

    edge_cmd = [python_exe, "main.py"]

    client_cmd = [
        python_exe,
        "mock_client/c_end_simulator.py",
        "--url",
        f"http://127.0.0.1:{args.port}",
        "--id",
        args.client_id,
        "--item",
        args.client_item,
        "--max",
        str(args.client_max),
    ]

    a2a_smoke_cmd = [
        python_exe,
        "mock_client/a2a_smoke_test.py",
        "--url",
        f"http://127.0.0.1:{args.port}",
        "--source",
        args.a2a_source,
        "--targets",
        args.a2a_targets,
    ]

    regression_cmd = [
        python_exe,
        "qa_regression_suite.py",
    ]
    if args.regression_online:
        regression_cmd.extend([
            "--online",
            "--url",
            f"http://127.0.0.1:{args.port}",
            "--merchant-id",
            args.a2a_source,
            "--merchant-key",
            os.getenv("HUB_MERCHANT_KEY", "merchant-shared-key"),
            "--a2a-source",
            args.a2a_source,
            "--a2a-targets",
            args.a2a_targets,
        ])

    procs = ProcGroup()

    try:
        print("[1/3] 启动云端 signaling_hub ...")
        p_cloud = _spawn(cloud_cmd, cwd=ROOT)
        procs.add(p_cloud)

        ok = _wait_health(f"http://127.0.0.1:{args.port}/health", timeout_sec=args.health_timeout)
        if not ok:
            raise RuntimeError("cloud_server 健康检查超时，请检查端口占用或依赖")
        print("✅ cloud_server 已就绪")

        print("[2/3] 启动 B端 edge_box ...")
        edge_dir = ROOT / "edge_box"
        if not edge_dir.exists():
            raise RuntimeError(f"edge_box 目录不存在: {edge_dir}")
        p_edge = _spawn(edge_cmd, cwd=edge_dir)
        procs.add(p_edge)
        time.sleep(2)
        if p_edge.poll() is not None:
            raise RuntimeError("edge_box 启动后立即退出，请检查 edge_box/.env 和日志")
        print("✅ edge_box 已启动")

        if not args.skip_client:
            print("[3/3] 启动 C端 mock_client (一次性任务) ...")
            rc = subprocess.call(client_cmd, cwd=str(ROOT))
            if rc != 0:
                print(f"⚠️ mock_client 退出码: {rc}")
            else:
                print("✅ mock_client 执行完成")

        if args.run_a2a_smoke:
            print("[4/5] 运行 A2A 冒烟测试 ...")
            rc2 = subprocess.call(a2a_smoke_cmd, cwd=str(ROOT))
            if rc2 != 0:
                print(f"⚠️ a2a_smoke_test 退出码: {rc2}")
            else:
                print("✅ a2a_smoke_test 通过")

        if args.run_regression:
            print("[5/5] 运行模块回归测试套件 ...")
            rc3 = subprocess.call(regression_cmd, cwd=str(ROOT))
            if rc3 != 0:
                print(f"⚠️ qa_regression_suite 退出码: {rc3}")
            else:
                print("✅ qa_regression_suite 通过")

        print("\n系统运行中。按 Ctrl+C 关闭所有子进程。")
        while True:
            if p_cloud.poll() is not None:
                raise RuntimeError("cloud_server 进程退出")
            if p_edge.poll() is not None:
                raise RuntimeError("edge_box 进程退出")
            time.sleep(1)

    except KeyboardInterrupt:
        print("\n收到 Ctrl+C，正在停止全部服务...")
    except Exception as e:
        print(f"\n❌ 启动/运行失败: {e}")
    finally:
        procs.terminate_all()
        print("已停止。")


if __name__ == "__main__":
    main()
