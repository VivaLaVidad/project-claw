from __future__ import annotations

import threading
import time
from pathlib import Path

from fastapi.testclient import TestClient

from a2a_signaling_server import app as signaling_app
from cloud_server.api_server_pro import app as siri_app, trade_coordinator
from config import settings


def test_signaling_offer_roundtrip() -> None:
    merchant_id = "merchant-smoke"
    with TestClient(signaling_app) as client:
        with client.websocket_connect(f"/ws/merchant/{merchant_id}") as ws:
            ws.send_json({"type": "register", "merchant_id": merchant_id})
            _ = ws.receive_json()

            captured: dict[str, object] = {}

            def merchant_worker() -> None:
                payload = ws.receive_json()
                assert payload["type"] == "intent_broadcast"
                captured["intent_id"] = payload["intent_id"]
                ws.send_json(
                    {
                        "type": "offer",
                        "intent_id": payload["intent_id"],
                        "merchant_id": merchant_id,
                        "reply_text": "可以接，十五分钟出餐",
                        "final_price": 14.5,
                        "match_score": 96.0,
                        "eta_minutes": 15,
                    }
                )

            t = threading.Thread(target=merchant_worker, daemon=True)
            t.start()
            resp = client.post(
                "/intent",
                json={
                    "client_id": "consumer-smoke",
                    "location": "TestZone",
                    "demand_text": "想吃牛肉面",
                    "max_price": 18,
                    "timeout": 2.0,
                },
            )
            t.join(timeout=3)
            assert resp.status_code == 200, resp.text
            data = resp.json()
            assert data["responded"] >= 1
            assert len(data["offers"]) >= 1
            assert data["offers"][0]["merchant_id"] == merchant_id
            assert captured["intent_id"] == data["intent_id"]


def test_siri_intent_and_showcase_log() -> None:
    event_file = Path(settings.SHOWCASE_EVENT_FILE)
    if event_file.exists():
        before = event_file.read_text(encoding="utf-8")
    else:
        before = ""

    pushed: list[tuple[str, object]] = []

    def fake_push(client_id: str, trade: object) -> dict[str, str]:
        pushed.append((client_id, trade))
        return {"ok": "1"}

    original = trade_coordinator.push_trade_request
    trade_coordinator.push_trade_request = fake_push  # type: ignore[assignment]
    try:
        with TestClient(siri_app) as client:
            resp = client.post(
                "/api/v1/siri_intent",
                json={"spoken_text": "帮我点牛肉面，15块以内", "client_id": "consumer-smoke"},
            )
            assert resp.status_code == 200, resp.text
            payload = resp.json()
            assert "speech_reply" in payload
            time.sleep(0.2)
            assert pushed, "trade request was not dispatched"
    finally:
        trade_coordinator.push_trade_request = original  # type: ignore[assignment]

    after = event_file.read_text(encoding="utf-8") if event_file.exists() else ""
    assert len(after) >= len(before)
    assert "vision_scan" in after
    assert "a2a_handshake" in after


def test_execute_trade_dispatch() -> None:
    merchant_id = "merchant-exec"
    with TestClient(signaling_app) as client:
        with client.websocket_connect(f"/ws/merchant/{merchant_id}") as ws:
            ws.send_json({"type": "register", "merchant_id": merchant_id})
            _ = ws.receive_json()

            resp = client.post(
                "/execute_trade",
                json={
                    "intent_id": "intent-001",
                    "client_id": "consumer-smoke",
                    "merchant_id": merchant_id,
                    "reply_text": "可以接，马上安排",
                    "final_price": 14.5,
                    "eta_minutes": 15,
                },
            )
            assert resp.status_code == 200, resp.text
            payload = ws.receive_json()
            assert payload["type"] == "execute_trade"
            assert payload["merchant_id"] == merchant_id
            assert payload["final_price"] == 14.5


if __name__ == "__main__":
    test_signaling_offer_roundtrip()
    test_siri_intent_and_showcase_log()
    test_execute_trade_dispatch()
    print("smoke tests passed")
