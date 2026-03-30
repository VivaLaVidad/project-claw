"""
Project Claw - edge_box/bootstrap.py
傻瓜式安装/配网引导：离线则开启热点 + Flask 配置页。
"""
from __future__ import annotations

import argparse
import logging
import os
import shlex
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict

from flask import Flask, render_template_string, request

LOG = logging.getLogger("claw.edge.bootstrap")

HTML = """
<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'/><meta name='viewport' content='width=device-width,initial-scale=1'/>
<title>Claw 快速配网</title>
<style>
body{margin:0;background:#0a0f1f;color:#e6edf7;font-family:"Microsoft YaHei","PingFang SC",sans-serif}
.wrap{min-height:100vh;display:flex;align-items:center;justify-content:center;padding:16px}
.card{width:min(560px,96vw);background:#101a31;border:1px solid #2b395f;border-radius:14px;padding:22px}
input,button{width:100%;padding:11px;border-radius:10px;box-sizing:border-box;margin-top:8px}
input{background:#0d1630;border:1px solid #3a4d7e;color:#e6edf7}
button{border:none;background:#14b8a6;color:#fff;font-weight:700;cursor:pointer}
label{display:block;margin-top:10px;color:#c7d2fe}.tip{color:#fbbf24;margin-top:12px}
</style></head><body><div class='wrap'><div class='card'>
<h2>Claw 商户盒子初始化</h2>
<p>请填写 WiFi 和商户号，提交后设备会自动重连并重启服务。</p>
<form method='post' action='/setup'>
<label>WiFi SSID</label><input name='ssid' required/>
<label>WiFi Password</label><input name='password' type='password' required/>
<label>商户号 MERCHANT_ID</label><input name='merchant_id' required/>
<button type='submit'>保存并重启服务</button>
</form>
{% if status %}<div class='tip'>{{status}}</div>{% endif %}
</div></div></body></html>
"""


class LedController:
    """LED 状态控制：
    - red_blink: 配网中
    - green_solid: 网络正常
    - yellow_blink: 撮合中

    默认通过环境变量 `CLAW_LED_COMMAND` 调用外部脚本。
    例如：CLAW_LED_COMMAND="/usr/local/bin/claw_led"
    则实际执行：/usr/local/bin/claw_led red_blink
    """

    def __init__(self):
        self._cmd = os.getenv("CLAW_LED_COMMAND", "").strip()

    def set(self, status: str):
        if not self._cmd:
            LOG.info("[LED] %s (no command configured)", status)
            return
        try:
            subprocess.run(f"{self._cmd} {shlex.quote(status)}", shell=True, check=False, timeout=5)
        except Exception as e:
            LOG.warning("[LED] set failed status=%s err=%s", status, e)


_LED = LedController()


def set_led_status(status: str):
    _LED.set(status)


class BootstrapManager:
    def __init__(self, env_path: Path, iface: str, ap_name: str, ap_password: str, service_name: str):
        self.env_path = env_path
        self.iface = iface
        self.ap_name = ap_name
        self.ap_password = ap_password
        self.service_name = service_name
        self.app = Flask(__name__)
        self._register_routes()

    @staticmethod
    def _run(cmd: str, check: bool = True, timeout: int = 20):
        LOG.info("[CMD] %s", cmd)
        p = subprocess.run(cmd, shell=True, check=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
        if check and p.returncode != 0:
            raise RuntimeError(f"cmd_failed: {cmd} => {p.stderr.strip()}")
        return p

    @staticmethod
    def _online() -> bool:
        checks = [
            "ping -c 1 -W 2 223.5.5.5 >/dev/null 2>&1",
            "ping -c 1 -W 2 8.8.8.8 >/dev/null 2>&1",
            "curl -s --max-time 3 https://www.baidu.com >/dev/null 2>&1",
        ]
        return any(subprocess.call(c, shell=True) == 0 for c in checks)

    def _load_env(self) -> Dict[str, str]:
        data: Dict[str, str] = {}
        if self.env_path.exists():
            for line in self.env_path.read_text(encoding="utf-8").splitlines():
                raw = line.strip()
                if raw and not raw.startswith("#") and "=" in raw:
                    k, v = raw.split("=", 1)
                    data[k.strip()] = v.strip()
        return data

    def _save_env(self, updates: Dict[str, str]):
        data = self._load_env()
        data.update(updates)
        self.env_path.write_text("\n".join([f"{k}={v}" for k, v in data.items()]) + "\n", encoding="utf-8")

    def _start_hotspot(self):
        # Linux 主路径：nmcli
        self._run(f"nmcli dev wifi hotspot ifname {self.iface} ssid {shlex.quote(self.ap_name)} password {shlex.quote(self.ap_password)}")

    def _connect_wifi(self, ssid: str, password: str):
        self._run(f"nmcli dev wifi connect {shlex.quote(ssid)} password {shlex.quote(password)} ifname {self.iface}")

    def _restart_main_service(self):
        self._run(f"systemctl restart {shlex.quote(self.service_name)}")

    def _register_routes(self):
        @self.app.get("/")
        def index():
            return render_template_string(HTML, status="")

        @self.app.post("/setup")
        def setup():
            ssid = (request.form.get("ssid") or "").strip()
            password = (request.form.get("password") or "").strip()
            merchant_id = (request.form.get("merchant_id") or "").strip()
            if not ssid or not password or not merchant_id:
                return render_template_string(HTML, status="请完整填写 SSID / Password / 商户号")

            try:
                set_led_status("red_blink")
                self._save_env({
                    "WIFI_SSID": ssid,
                    "WIFI_PASSWORD": password,
                    "MERCHANT_ID": merchant_id,
                })
                self._connect_wifi(ssid, password)

                deadline = time.time() + 35
                ok = False
                while time.time() < deadline:
                    if self._online():
                        ok = True
                        break
                    time.sleep(2)
                if not ok:
                    raise RuntimeError("wifi_connect_timeout")

                set_led_status("green_solid")
                self._restart_main_service()
                return "<h3>✅ 配置成功，主服务正在重启，请稍候。</h3>"
            except Exception as e:
                LOG.exception("setup failed: %s", e)
                set_led_status("red_blink")
                return render_template_string(HTML, status=f"配置失败：{e}")

    def run(self, port: int):
        if self._online():
            set_led_status("green_solid")
            LOG.info("network ok, no bootstrap needed")
            return

        LOG.warning("network offline, entering setup AP mode")
        set_led_status("red_blink")
        self._start_hotspot()

        def _shutdown(*_):
            try:
                self._run(f"nmcli connection down {shlex.quote(self.ap_name)}", check=False)
            except Exception:
                pass

        signal.signal(signal.SIGINT, _shutdown)
        signal.signal(signal.SIGTERM, _shutdown)
        self.app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)


def main():
    p = argparse.ArgumentParser(description="Project Claw bootstrap installer")
    p.add_argument("--env-path", default=str((Path(__file__).resolve().parent / ".env")))
    p.add_argument("--iface", default=os.getenv("CLAW_WIFI_IFACE", "wlan0"))
    p.add_argument("--ap-name", default=os.getenv("CLAW_SETUP_AP_NAME", "Claw-Setup"))
    p.add_argument("--ap-password", default=os.getenv("CLAW_SETUP_AP_PASSWORD", "12345678"))
    p.add_argument("--service-name", default=os.getenv("CLAW_SERVICE_NAME", "claw-edge.service"))
    p.add_argument("--port", type=int, default=int(os.getenv("CLAW_SETUP_PORT", "80")))
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s - %(message)s")
    BootstrapManager(
        env_path=Path(args.env_path),
        iface=args.iface,
        ap_name=args.ap_name,
        ap_password=args.ap_password,
        service_name=args.service_name,
    ).run(args.port)


if __name__ == "__main__":
    main()
