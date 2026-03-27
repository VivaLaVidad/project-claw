from __future__ import annotations

import threading
import time
from typing import Any
from uuid import uuid4

from fastapi.testclient import TestClient

from a2a_signaling_server import app
from config import settings


def _auth_headers() -> dict[str, str]:
    if settings.INTERNAL_API_TOKEN:
        return {"x-internal-token": settings.INTERNAL_API_TOKEN}
    return {}


def test_a2a_intent_offer_decision_closed_loop() -> None:
    merchant_id = "merchant-a2a-smoke"
    client_id = "client-a2a-smoke"

    with TestClient(app) as client:
        with client.websocket_connect(f"/ws/a2a/merchant/{merchant_id}") as ws:
            captured: dict[str, Any] = {}
            done = threading.Event()

            def merchant_worker() -> None:
                intent_msg = ws.receive_json()
                assert intent_msg["type"] == "a2a_trade_intent"

                intent = intent_msg["intent"]
                offer_payload = {
                    "type": "a2a_merchant_offer",
                    "offer": {
                        "offer_id": str(uuid4()),
                        "intent_id": intent["intent_id"],
                        "merchant_id": merchant_id,
                        "offered_price": 15.8,
                        "is_accepted": True,
                        "reason": "可接单，15分钟送达",
                    },
                }
                ws.send_json(offer_payload)

                decision_msg = ws.receive_json()
                captured["decision_msg"] = decision_msg
                done.set()

            t = threading.Thread(target=merchant_worker, daemon=True)
            t.start()

            intent_resp = client.post(
                "/a2a/intent",
                json={
                    "client_id": client_id,
                    "item_name": "牛肉面",
                    "expected_price": 16.0,
                    "max_distance_km": 8.0,
                },
                headers=_auth_headers(),
            )
            assert intent_resp.status_code == 200, intent_resp.text
            result = intent_resp.json()
            assert result["responded"] >= 1
            assert result["offers"], "no offers returned"

            top_offer = result["offers"][0]
            decision_resp = client.post(
                "/a2a/decision",
                params={"final_price": top_offer["offered_price"]},
                json={
                    "offer_id": top_offer["offer_id"],
                    "client_id": client_id,
                    "decision": "ACCEPT",
                },
                headers=_auth_headers(),
            )
            assert decision_resp.status_code == 200, decision_resp.text

            assert done.wait(timeout=3), "merchant did not receive trade decision"
            decision_msg = captured["decision_msg"]
            assert decision_msg["type"] == "a2a_trade_decision"
            assert decision_msg["decision"]["decision"] == "ACCEPT"
            assert float(decision_msg["final_price"]) == float(top_offer["offered_price"])

            t.join(timeout=1)


if __name__ == "__main__":
    start = time.time()
    test_a2a_intent_offer_decision_closed_loop()
    elapsed = (time.time() - start) * 1000
    print(f"a2a e2e smoke passed in {elapsed:.1f}ms")
