"""
Project Claw - Professional regression suite

目标：
1) 覆盖各模块基础可用性（shared/cloud/edge/mock/mini-program）
2) 覆盖核心跨模块协作能力（协议 + A2A + 社交匹配）
3) 可选在线联调（Hub REST + A2A 冒烟）
"""
from __future__ import annotations

import argparse
import asyncio
import json
import py_compile
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


@dataclass
class CaseResult:
    name: str
    status: str  # PASS / FAIL / SKIP
    detail: str = ""


def _run_case(name: str, fn: Callable[[], str], optional_missing_ok: tuple[str, ...]) -> CaseResult:
    try:
        detail = fn() or "ok"
        return CaseResult(name=name, status="PASS", detail=detail)
    except ModuleNotFoundError as e:
        mod = (getattr(e, "name", "") or "").split(".")[0]
        if mod and mod in optional_missing_ok:
            return CaseResult(name=name, status="SKIP", detail=f"missing_optional_dependency:{mod}")
        return CaseResult(name=name, status="FAIL", detail=str(e))
    except Exception as e:
        return CaseResult(name=name, status="FAIL", detail=str(e))


def case_compile_all_python() -> str:
    py_files = [
        p for p in ROOT.rglob("*.py")
        if "__pycache__" not in p.parts and ".cursor" not in p.parts
    ]
    for p in py_files:
        py_compile.compile(str(p), doraise=True)
    return f"compiled={len(py_files)}"


def case_shared_protocol_roundtrip() -> str:
    from shared.claw_protocol import MsgType, SignalEnvelope, TradeRequest

    req = TradeRequest(
        client_id="test-client",
        item_name="牛肉面",
        demand_text="要一份牛肉面，20元以内",
        max_price=20,
    )
    env = SignalEnvelope.wrap(MsgType.TRADE_REQUEST, "client", req)
    encoded = env.model_dump_json()
    env2 = SignalEnvelope.model_validate_json(encoded)
    req2 = TradeRequest(**env2.payload)
    assert req2.item_name == "牛肉面"
    assert req2.max_price == 20
    return "signal envelope roundtrip ok"


def case_shared_a2a_handshake() -> str:
    from shared.a2a_handshake import build_packet, open_packet

    packet = build_packet(
        source_id="box-A",
        target_id="box-B",
        msg_type="trade_request",
        payload={"kind": "trade_request", "trade_request": {"request_id": "r1"}},
    )
    opened = open_packet(packet, expected_target_id="box-B")
    assert opened["payload"]["kind"] == "trade_request"

    bad = packet.model_copy(deep=True)
    bad.signature = "0" * len(packet.signature)
    try:
        open_packet(bad, expected_target_id="box-B")
        raise AssertionError("tampered signature should fail")
    except ValueError as e:
        assert "bad_packet_signature" in str(e)

    return "encrypt/decrypt + signature verify ok"


def case_cloud_social_coordinator() -> str:
    from shared.claw_protocol import GeoCoord, SocialIntent
    from cloud_server.social_coordinator import SocialCoordinator

    async def _run():
        c = SocialCoordinator(similarity_threshold=0.9, max_distance_m=2000, ttl_sec=60, match_cooldown_sec=1)
        q1 = await c.register_sse("c1")
        q2 = await c.register_sse("c2")
        vec = [0.1] * 1024

        await c.upsert_intent(SocialIntent(client_id="c1", persona_vector=vec, location=GeoCoord(lat=31.23, lng=121.47), topic_hint="美食"))
        events = await c.upsert_intent(SocialIntent(client_id="c2", persona_vector=vec, location=GeoCoord(lat=31.231, lng=121.471), topic_hint="探店"))
        assert len(events) >= 2
        assert not q1.empty() and not q2.empty()

    asyncio.run(_run())
    return "social matching + SSE queue ok"


def case_edge_bootstrap_env_rw() -> str:
    from edge_box.bootstrap import BootstrapManager

    with tempfile.TemporaryDirectory() as td:
        env_path = Path(td) / ".env"
        mgr = BootstrapManager(
            env_path=env_path,
            iface="wlan0",
            ap_name="Claw-Setup",
            ap_password="12345678",
            service_name="claw-edge.service",
        )
        mgr._save_env({"MERCHANT_ID": "box-001", "WIFI_SSID": "demo"})
        data = mgr._load_env()
        assert data.get("MERCHANT_ID") == "box-001"
        assert data.get("WIFI_SSID") == "demo"
    return "bootstrap env load/save ok"


def case_edge_main_led_decoupled() -> str:
    p = ROOT / "edge_box" / "main.py"
    text = p.read_text(encoding="utf-8")
    assert "CLAW_LED_COMMAND" in text
    return "main LED is command-based"


def case_mock_merchant_match() -> str:
    from mock_merchants.multi_merchant_simulator import match_item

    menu = {
        "牛肉面": {"price": 18, "floor": 14, "spec": "大碗", "desc": "现熬牛骨汤"},
        "水饺": {"price": 10, "floor": 7, "spec": "10个", "desc": "手工"},
    }
    matched = match_item(menu, "牛肉", "我想吃牛肉面")
    assert matched is not None
    return "mock merchant item matching ok"


def case_miniprogram_config_consistency() -> str:
    cfg = (ROOT / "mini_program_app" / "utils" / "config.js").read_text(encoding="utf-8")
    api = (ROOT / "mini_program_app" / "utils" / "api.js").read_text(encoding="utf-8")

    m = re.search(r"BASE_URL\s*=\s*['\"]([^'\"]+)['\"]", cfg)
    assert m, "BASE_URL not found"
    base_url = m.group(1)
    assert base_url.startswith("http"), "BASE_URL must be http/https"

    assert "replace(/^https:/, 'wss:')" in api
    assert "replace(/^http:/, 'ws:')" in api
    return "mini-program http/ws conversion strategy ok"


def case_online_hub_health(base_url: str) -> str:
    with urllib.request.urlopen(f"{base_url.rstrip('/')}/health", timeout=5) as resp:
        if resp.status < 200 or resp.status >= 300:
            raise RuntimeError(f"health_bad_status:{resp.status}")
        body = json.loads(resp.read().decode("utf-8"))
    return f"health ok merchants={body.get('merchants', 'n/a')}"


def case_online_auth(base_url: str, merchant_id: str, merchant_key: str) -> str:
    req_client = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/v1/auth/client",
        data=json.dumps({"client_id": "regression-client"}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req_client, timeout=5) as resp:
        c = json.loads(resp.read().decode("utf-8"))
    assert c.get("token"), "client token empty"

    req_merchant = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/v1/auth/merchant",
        data=json.dumps({"merchant_id": merchant_id, "key": merchant_key}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req_merchant, timeout=5) as resp:
        m = json.loads(resp.read().decode("utf-8"))
    assert m.get("token"), "merchant token empty"

    return "auth client+merchant ok"


def case_online_a2a_smoke(base_url: str, source: str, targets: str, merchant_key: str) -> str:
    cmd = [
        sys.executable,
        str(ROOT / "mock_client" / "a2a_smoke_test.py"),
        "--url",
        base_url,
        "--source",
        source,
        "--targets",
        targets,
        "--merchant-key",
        merchant_key,
        "--timeout",
        "20",
    ]
    rc = subprocess.call(cmd, cwd=str(ROOT))
    if rc != 0:
        raise RuntimeError(f"a2a_smoke_failed_exit={rc}")
    return "a2a smoke passed"


def main():
    p = argparse.ArgumentParser(description="Project Claw professional regression suite")
    p.add_argument("--online", action="store_true", help="启用在线联调测试（需要 Hub/商家在线）")
    p.add_argument("--strict-deps", action="store_true", help="缺失可选依赖时按 FAIL 处理（默认 SKIP）")
    p.add_argument("--url", default="http://127.0.0.1:8765", help="Hub HTTP URL")
    p.add_argument("--merchant-id", default="box-001")
    p.add_argument("--merchant-key", default="merchant-shared-key")
    p.add_argument("--a2a-source", default="box-001")
    p.add_argument("--a2a-targets", default="box-002,box-003,box-004")
    args = p.parse_args()

    cases = [
        ("compile_all_python", case_compile_all_python),
        ("shared_protocol_roundtrip", case_shared_protocol_roundtrip),
        ("shared_a2a_handshake", case_shared_a2a_handshake),
        ("cloud_social_coordinator", case_cloud_social_coordinator),
        ("edge_bootstrap_env_rw", case_edge_bootstrap_env_rw),
        ("edge_main_led_decoupled", case_edge_main_led_decoupled),
        ("mock_merchant_match", case_mock_merchant_match),
        ("miniprogram_config_consistency", case_miniprogram_config_consistency),
    ]

    if args.online:
        cases.extend([
            ("online_hub_health", lambda: case_online_hub_health(args.url)),
            ("online_auth", lambda: case_online_auth(args.url, args.merchant_id, args.merchant_key)),
            ("online_a2a_smoke", lambda: case_online_a2a_smoke(args.url, args.a2a_source, args.a2a_targets, args.merchant_key)),
        ])

    started = time.time()
    results: list[CaseResult] = []
    optional_missing_ok = () if args.strict_deps else ("cryptography", "flask")

    for name, fn in cases:
        r = _run_case(name, fn, optional_missing_ok=optional_missing_ok)
        results.append(r)
        print(f"[{r.status}] {r.name} -> {r.detail}")

    passed = sum(1 for r in results if r.status == "PASS")
    skipped = sum(1 for r in results if r.status == "SKIP")
    failed = sum(1 for r in results if r.status == "FAIL")
    total = len(results)
    elapsed = round(time.time() - started, 2)

    print("\n" + "=" * 72)
    print(f"Regression Summary: passed={passed} skipped={skipped} failed={failed} total={total} elapsed={elapsed}s")
    print("=" * 72)

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
