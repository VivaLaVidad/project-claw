from __future__ import annotations

import json
import threading
import time
from uuid import uuid4

from fastapi.testclient import TestClient

from a2a_signaling_server import app
from config import settings


def _auth_headers() -> dict[str, str]:
    if settings.INTERNAL_API_TOKEN:
        return {"x-internal-token": settings.INTERNAL_API_TOKEN}
    return {}


def test_a2a_dialogue_multi_turn_closed_loop() -> None:
    client_id = "client-dialogue-smoke"
    merchant_id = "merchant-dialogue-smoke"

    with TestClient(app) as client:
        with client.websocket_connect(f"/ws/a2a/dialogue/merchant/{merchant_id}") as merchant_ws:
            captured: dict[str, str] = {}
            done = threading.Event()

            def merchant_worker() -> None:
                first = merchant_ws.receive_json()
                assert first["type"] == "a2a_dialogue_turn"
                first_turn = first["turn"]
                captured["session_id"] = first_turn["session_id"]
                captured["intent_id"] = first_turn["intent_id"]

                reply_turn = {
                    "type": "a2a_dialogue_turn",
                    "turn": {
                        "turn_id": str(uuid4()),
                        "session_id": first_turn["session_id"],
                        "intent_id": first_turn["intent_id"],
                        "round": 1,
                        "sender_role": "MERCHANT",
                        "sender_id": merchant_id,
                        "receiver_role": "CLIENT",
                        "receiver_id": client_id,
                        "text": "老板这边最低 15.5 元，15 分钟送达",
                        "offered_price": 15.5,
                        "strategy_hint": "先报可履约最低价",
                        "timestamp": time.time(),
                    },
                }
                merchant_ws.send_text(json.dumps(reply_turn, ensure_ascii=False))

                second = merchant_ws.receive_json()
                assert second["type"] == "a2a_dialogue_turn"
                done.set()

            t = threading.Thread(target=merchant_worker, daemon=True)
            t.start()

            start_resp = client.post(
                "/a2a/dialogue/start",
                json={
                    "intent": {
                        "intent_id": str(uuid4()),
                        "client_id": client_id,
                        "item_name": "牛肉面",
                        "expected_price": 16.0,
                        "max_distance_km": 8.0,
                        "timestamp": time.time(),
                    },
                    "merchant_id": merchant_id,
                    "opening_text": "预算 16 元，有更优惠方案吗？",
                },
                headers=_auth_headers(),
            )
            assert start_resp.status_code == 200, start_resp.text
            session_id = start_resp.json()["session_id"]

            turn_resp = client.post(
                "/a2a/dialogue/client_turn",
                json={
                    "session_id": session_id,
                    "client_id": client_id,
                    "text": "如果 15 元能下单，我马上拍",
                    "expected_price": 15.0,
                },
                headers=_auth_headers(),
            )
            assert turn_resp.status_code == 200, turn_resp.text

            assert done.wait(timeout=3), "merchant did not receive second turn"

            detail_resp = client.get(f"/a2a/dialogue/{session_id}", headers=_auth_headers())
            assert detail_resp.status_code == 200, detail_resp.text
            data = detail_resp.json()
            assert data["session"]["client_id"] == client_id
            assert data["session"]["merchant_id"] == merchant_id
            assert len(data["turns"]) >= 3

            close_resp = client.post(f"/a2a/dialogue/{session_id}/close", headers=_auth_headers())
            assert close_resp.status_code == 200, close_resp.text

            t.join(timeout=1)


if __name__ == "__main__":
    started = time.time()
    test_a2a_dialogue_multi_turn_closed_loop()
    elapsed_ms = (time.time() - started) * 1000
    print(f"a2a dialogue smoke passed in {elapsed_ms:.1f}ms")
