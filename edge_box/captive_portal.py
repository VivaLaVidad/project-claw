"""
Project Claw v16.0 - edge_box/captive_portal.py
离线配网门户：开启 Claw-Setup AP 并提供 WiFi 配置页面
"""
from __future__ import annotations

import html
import json
import logging
import os
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

logger = logging.getLogger("claw.edge.captive")

_AP_SSID = os.getenv("CLAW_SETUP_AP_SSID", "Claw-Setup")
_AP_PASS = os.getenv("CLAW_SETUP_AP_PASS", "clawsetup888")
_PORT = int(os.getenv("CLAW_SETUP_PORT", "8899"))


def _run_cmd(command: str):
    try:
        subprocess.run(command, shell=True, check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except Exception as e:
        logger.warning("[CaptivePortal] command failed: %s err=%s", command, e)


def enable_setup_ap(ssid: str = _AP_SSID, password: str = _AP_PASS):
    """跨平台尽力开启热点（Windows/Linux）"""
    if os.name == "nt":
        _run_cmd(f'netsh wlan set hostednetwork mode=allow ssid="{ssid}" key="{password}"')
        _run_cmd("netsh wlan start hostednetwork")
    else:
        _run_cmd(f"nmcli dev wifi hotspot ifname wlan0 ssid '{ssid}' password '{password}'")


def disable_setup_ap():
    if os.name == "nt":
        _run_cmd("netsh wlan stop hostednetwork")
    else:
        _run_cmd("nmcli connection down Hotspot")


def _env_path() -> Path:
    return Path(__file__).with_name(".env")


def _upsert_env(kv: dict):
    path = _env_path()
    existing = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                existing[k.strip()] = v.strip()
    existing.update({k: str(v) for k, v in kv.items()})
    lines = [f"{k}={v}" for k, v in existing.items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


class _PortalHandler(BaseHTTPRequestHandler):
    def _reply(self, code: int, body: str, content_type: str = "text/html; charset=utf-8"):
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):  # noqa: A003
        logger.info("[CaptivePortal] " + fmt, *args)

    def do_GET(self):  # noqa: N802
        path = urlparse(self.path).path
        if path == "/health":
            self._reply(200, json.dumps({"ok": True, "ts": time.time()}), "application/json")
            return

        html_page = f"""
<!doctype html><html><head><meta charset=\"utf-8\"><title>Claw Setup</title>
<style>
body {{ font-family: -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; background:#0a0e27; color:#fff; padding:24px; }}
.card {{ max-width:520px; margin:24px auto; padding:20px; border-radius:14px; background:rgba(255,255,255,0.08); border:1px solid rgba(255,255,255,0.15); }}
input {{ width:100%; padding:12px; margin:8px 0; border-radius:10px; border:1px solid #3a3a58; background:#121735; color:#fff; }}
button {{ width:100%; padding:12px; border:0; border-radius:10px; background:#00ff41; color:#000; font-weight:700; }}
.small {{ color:#a0a0a0; font-size:12px; }}
</style></head>
<body><div class=\"card\"><h2>Project Claw 离线配网</h2>
<form method=\"POST\" action=\"/setup\">
<input name=\"ssid\" placeholder=\"WiFi 名称 (SSID)\" required />
<input name=\"password\" type=\"password\" placeholder=\"WiFi 密码\" required />
<input name=\"signaling_url\" placeholder=\"云端 URL (可选) 例如 https://api.projectclaw.cn\" />
<button type=\"submit\">保存并应用</button>
</form>
<p class=\"small\">当前 AP: {html.escape(_AP_SSID)}，保存后请重启 edge 服务。</p>
</div></body></html>
"""
        self._reply(200, html_page)

    def do_POST(self):  # noqa: N802
        path = urlparse(self.path).path
        if path != "/setup":
            self._reply(404, "not_found")
            return

        length = int(self.headers.get("Content-Length", "0"))
        payload = self.rfile.read(length).decode("utf-8")
        form = parse_qs(payload)
        ssid = (form.get("ssid", [""])[0] or "").strip()
        pwd = (form.get("password", [""])[0] or "").strip()
        signaling_url = (form.get("signaling_url", [""])[0] or "").strip()

        if not ssid or not pwd:
            self._reply(400, "ssid_or_password_empty")
            return

        updates = {
            "WIFI_SSID": ssid,
            "WIFI_PASSWORD": pwd,
        }
        if signaling_url:
            updates["SIGNALING_URL"] = signaling_url
        _upsert_env(updates)

        self._reply(200, "<html><body><h3>配置已保存，请重启盒子服务。</h3></body></html>")


class CaptivePortal:
    def __init__(self, host: str = "0.0.0.0", port: int = _PORT):
        self.host = host
        self.port = port
        self._server = ThreadingHTTPServer((host, port), _PortalHandler)
        self._thread: threading.Thread | None = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        enable_setup_ap()
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True, name="ClawCaptivePortal")
        self._thread.start()
        logger.info("[CaptivePortal] started at http://%s:%s", self.host, self.port)

    def stop(self):
        try:
            self._server.shutdown()
            self._server.server_close()
        finally:
            disable_setup_ap()
            logger.info("[CaptivePortal] stopped")
