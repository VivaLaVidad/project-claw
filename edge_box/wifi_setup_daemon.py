from __future__ import annotations

import argparse
import atexit
import logging
import os
import shlex
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Dict, Optional

from flask import Flask, Response, redirect, render_template_string, request

LOG = logging.getLogger("claw.edge.wifi_setup")

HTML = """
<!doctype html><html lang='zh-CN'><head><meta charset='utf-8' />
<meta name='viewport' content='width=device-width, initial-scale=1' />
<title>Claw-Setup 配网</title>
<style>
body{margin:0;font-family:"Segoe UI","PingFang SC",sans-serif;background:#0b1020;color:#e5e7eb}
.wrap{min-height:100vh;display:flex;align-items:center;justify-content:center;padding:16px}
.card{width:min(560px,96vw);background:#111827;border:1px solid #334155;border-radius:14px;padding:20px}
input,button{width:100%;box-sizing:border-box;padding:12px;border-radius:10px;margin-top:8px}
input{background:#0f172a;border:1px solid #475569;color:#e5e7eb}button{border:none;background:#0284c7;color:#fff;font-weight:700}
label{display:block;margin-top:12px;color:#cbd5e1}.status{margin-top:12px;color:#fbbf24}
</style></head><body><div class='wrap'><div class='card'>
<h2>Claw 设备配网</h2><p>填写 WiFi 与商户邀请码后，设备将自动入网并启动主程序。</p>
<form method='post' action='/setup'>
<label>WiFi SSID</label><input name='ssid' required />
<label>WiFi 密码</label><input name='password' type='password' required />
<label>商户唯一邀请码</label><input name='invite_code' required />
<button type='submit'>保存并连接</button></form>
{% if status %}<div class='status'>{{ status }}</div>{% endif %}
</div></div></body></html>
"""


class WifiSetupDaemon:
    def __init__(self, env_path: Path, ap_name: str, ap_password: str, iface: str, main_entry: str):
        self.env_path = env_path
        self.ap_name = ap_name
        self.ap_password = ap_password
        self.iface = iface
        self.main_entry = main_entry
        self.app = Flask(__name__)
        self._dnsmasq_proc: Optional[subprocess.Popen] = None
        self._register_routes()

    @staticmethod
    def _run(cmd: str, check: bool = True, timeout: int = 25) -> subprocess.CompletedProcess:
        LOG.info("[CMD] %s", cmd)
        p = subprocess.run(cmd, shell=True, check=False, timeout=timeout, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if check and p.returncode != 0:
            raise RuntimeError(f"command_failed: {cmd} | {p.stderr.strip()}")
        return p

    @staticmethod
    def _has(bin_name: str) -> bool:
        return subprocess.call(f"command -v {shlex.quote(bin_name)} >/dev/null 2>&1", shell=True) == 0

    @staticmethod
    def _is_online() -> bool:
        cmds = [
            "ping -c 1 -W 2 223.5.5.5 >/dev/null 2>&1",
            "ping -c 1 -W 2 8.8.8.8 >/dev/null 2>&1",
            "curl -s --max-time 3 https://www.baidu.com >/dev/null 2>&1",
        ]
        return any(subprocess.call(c, shell=True) == 0 for c in cmds)

    def _load_env(self) -> Dict[str, str]:
        data: Dict[str, str] = {}
        if self.env_path.exists():
            for line in self.env_path.read_text(encoding="utf-8").splitlines():
                raw = line.strip()
                if raw and not raw.startswith("#") and "=" in raw:
                    k, v = raw.split("=", 1)
                    data[k.strip()] = v.strip()
        return data

    def _save_env(self, updates: Dict[str, str]) -> None:
        data = self._load_env()
        data.update(updates)
        self.env_path.write_text("\n".join([f"{k}={v}" for k, v in data.items()]) + "\n", encoding="utf-8")
        LOG.info("[ENV] saved to %s", self.env_path)

    def _start_ap(self) -> None:
        if self._has("nmcli"):
            self._run(f"nmcli dev wifi hotspot ifname {self.iface} ssid {shlex.quote(self.ap_name)} password {shlex.quote(self.ap_password)}")
            LOG.info("[AP] started hotspot %s", self.ap_name)
            return
        if self._has("iw"):
            self._run(f"ip link set {self.iface} down", check=False)
            self._run(f"iw dev {self.iface} set type __ap")
            self._run(f"ip link set {self.iface} up")
            LOG.info("[AP] switched iface to AP mode")
            return
        raise RuntimeError("nmcli_or_iw_required")

    def _stop_ap(self) -> None:
        if self._has("nmcli"):
            self._run(f"nmcli connection down {shlex.quote(self.ap_name)}", check=False)
            self._run(f"nmcli connection delete {shlex.quote(self.ap_name)}", check=False)
        elif self._has("iw"):
            self._run(f"ip link set {self.iface} down", check=False)
            self._run(f"iw dev {self.iface} set type managed", check=False)
            self._run(f"ip link set {self.iface} up", check=False)
        LOG.info("[AP] stopped")

    def _start_dns_hijack(self) -> None:
        if self._has("dnsmasq"):
            fd, conf = tempfile.mkstemp(prefix="claw_dnsmasq_", suffix=".conf")
            os.close(fd)
            Path(conf).write_text("\n".join([
                f"interface={self.iface}",
                "bind-interfaces",
                "address=/#/192.168.4.1",
                "port=53",
                "dhcp-authoritative",
            ]) + "\n", encoding="utf-8")
            self._dnsmasq_proc = subprocess.Popen(["dnsmasq", "-C", conf])
            LOG.info("[CAPTIVE] dnsmasq started")
        else:
            LOG.warning("[CAPTIVE] dnsmasq missing, DNS hijack skipped")

        self._run("iptables -t nat -A PREROUTING -p tcp --dport 80 -j REDIRECT --to-ports 80", check=False)

    def _stop_dns_hijack(self) -> None:
        self._run("iptables -t nat -D PREROUTING -p tcp --dport 80 -j REDIRECT --to-ports 80", check=False)
        if self._dnsmasq_proc and self._dnsmasq_proc.poll() is None:
            self._dnsmasq_proc.terminate()
            self._dnsmasq_proc.wait(timeout=5)
            LOG.info("[CAPTIVE] dnsmasq stopped")

    def _connect_wifi(self, ssid: str, password: str) -> None:
        if self._has("nmcli"):
            self._run(f"nmcli dev wifi connect {shlex.quote(ssid)} password {shlex.quote(password)} ifname {self.iface}")
            return
        if self._has("cmd"):
            self._run(f"cmd wifi connect-network {shlex.quote(ssid)} open", check=False)
            return
        raise RuntimeError("wifi_connect_not_supported")

    def _wait_online(self, sec: int = 40) -> bool:
        end = time.time() + sec
        while time.time() < end:
            if self._is_online():
                return True
            time.sleep(2)
        return False

    def _launch_main(self) -> None:
        entry = Path(self.main_entry)
        if not entry.is_absolute():
            entry = (Path(__file__).resolve().parent.parent / self.main_entry).resolve()
        if not entry.exists():
            fallback = (Path(__file__).resolve().parent / "main.py").resolve()
            if fallback.exists():
                LOG.warning("[MAIN] %s missing, fallback to %s", entry, fallback)
                entry = fallback
            else:
                raise FileNotFoundError(f"main_entry_not_found:{entry}")
        cmd = f"{shlex.quote(sys.executable)} {shlex.quote(str(entry))}"
        LOG.info("[MAIN] launch: %s", cmd)
        subprocess.Popen(cmd, shell=True)

    def _register_routes(self) -> None:
        @self.app.get("/")
        def root() -> str:
            return render_template_string(HTML, status="")

        @self.app.get("/generate_204")
        @self.app.get("/hotspot-detect.html")
        @self.app.get("/connecttest.txt")
        def captive_probe() -> Response:
            return redirect("/", code=302)

        @self.app.post("/setup")
        def setup() -> str:
            ssid = (request.form.get("ssid") or "").strip()
            password = (request.form.get("password") or "").strip()
            invite_code = (request.form.get("invite_code") or "").strip()
            if not ssid or not password or not invite_code:
                return render_template_string(HTML, status="请完整填写 SSID、密码、邀请码")
            try:
                self._save_env({
                    "WIFI_SSID": ssid,
                    "WIFI_PASSWORD": password,
                    "MERCHANT_INVITE_CODE": invite_code,
                })
                self._stop_dns_hijack()
                self._stop_ap()
                self._connect_wifi(ssid, password)
                if not self._wait_online(40):
                    raise RuntimeError("wifi_connect_timeout")
                self._launch_main()
                return "<h3>✅ 配网成功，主进程已启动，可关闭本页面。</h3>"
            except Exception as e:
                LOG.exception("[SETUP] failed: %s", e)
                return render_template_string(HTML, status=f"配置失败：{e}")

    def run(self, port: int) -> None:
        if self._is_online():
            LOG.info("[NET] online, direct launch main")
            self._launch_main()
            return

        LOG.warning("[NET] offline, enter AP setup mode")
        self._start_ap()
        self._start_dns_hijack()

        def _shutdown(*_):
            self._stop_dns_hijack()
            self._stop_ap()

        signal.signal(signal.SIGINT, _shutdown)
        signal.signal(signal.SIGTERM, _shutdown)
        atexit.register(self._stop_dns_hijack)
        atexit.register(self._stop_ap)

        self.app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)


def main() -> None:
    p = argparse.ArgumentParser(description="Project Claw headless WiFi setup daemon")
    p.add_argument("--env-path", default=str((Path(__file__).resolve().parent / ".env")))
    p.add_argument("--ap-name", default=os.getenv("CLAW_SETUP_AP_NAME", "Claw-Setup"))
    p.add_argument("--ap-password", default=os.getenv("CLAW_SETUP_AP_PASSWORD", "12345678"))
    p.add_argument("--iface", default=os.getenv("CLAW_WIFI_IFACE", "wlan0"))
    p.add_argument("--main-entry", default=os.getenv("CLAW_MAIN_ENTRY", "lobster_mvp.py"))
    p.add_argument("--port", type=int, default=int(os.getenv("CLAW_SETUP_PORT", "80")))
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s - %(message)s")
    daemon = WifiSetupDaemon(Path(args.env_path), args.ap_name, args.ap_password, args.iface, args.main_entry)
    daemon.run(args.port)


if __name__ == "__main__":
    main()
