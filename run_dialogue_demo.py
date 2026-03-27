import asyncio
import json
import time
import uuid
from collections import defaultdict

import requests
import websockets

BASE_HTTP = "http://127.0.0.1:8765"
BASE_WS = "ws://127.0.0.1:8765"

CLIENT_ID = "client-real-001"
MERCHANT_ID = "box-001"

# 如果你设置了 INTERNAL_API_TOKEN，就填上；没设置就留空
INTERNAL_TOKEN = ""

HEADERS = {"Content-Type": "application/json"}
if INTERNAL_TOKEN:
    HEADERS["x-internal-token"] = INTERNAL_TOKEN

# 用来追踪每轮的回复
received_turns: dict[int, list] = defaultdict(list)
turn_event = asyncio.Event()


async def ws_listener() -> None:
    url = f"{BASE_WS}/ws/a2a/dialogue/client/{CLIENT_ID}"
    async with websockets.connect(url) as ws:
        print(f"[C-WS] connected: {url}")
        print("[C-WS] 你现在看到的就是 C/B agent 实时交流")
        try:
            while True:
                msg = await ws.recv()
                data = json.loads(msg)
                turn = data.get("turn", {})
                round_no = turn.get("round", 0)
                sender_role = turn.get("sender_role", "")
                text = turn.get("text", "")[:60]
                print(f"[C-WS] <- round={round_no} {sender_role}: {text}")

                received_turns[round_no].append(turn)
                turn_event.set()
        except asyncio.CancelledError:
            print("[C-WS] listener cancelled")


def http_setup_profiles() -> None:
    client_profile = {
        "client_id": CLIENT_ID,
        "budget_min": 12.0,
        "budget_max": 18.0,
        "price_sensitivity": 0.9,
        "time_urgency": 0.7,
        "quality_preference": 0.6,
        "custom_tags": ["学生", "价格敏感"],
    }
    merchant_profile = {
        "merchant_id": MERCHANT_ID,
        "bottom_price": 14.0,
        "normal_price": 16.5,
        "max_discount_rate": 0.2,
        "delivery_time_minutes": 15,
        "quality_score": 0.88,
        "service_score": 0.85,
        "inventory_status": {"牛肉面": 30},
        "custom_tags": ["可议价", "高履约"],
    }

    rc = requests.post(
        f"{BASE_HTTP}/a2a/dialogue/profile/client",
        headers=HEADERS,
        data=json.dumps(client_profile),
        timeout=15,
    )
    rc.raise_for_status()

    rm = requests.post(
        f"{BASE_HTTP}/a2a/dialogue/profile/merchant",
        headers=HEADERS,
        data=json.dumps(merchant_profile),
        timeout=15,
    )
    rm.raise_for_status()

    print("[HTTP] profiles ready -> client + merchant")


def http_start_dialogue() -> str:
    body = {
        "intent": {
            "intent_id": str(uuid.uuid4()),
            "client_id": CLIENT_ID,
            "item_name": "牛肉面",
            "expected_price": 16.0,
            "max_distance_km": 8.0,
            "timestamp": time.time(),
        },
        "merchant_id": MERCHANT_ID,
        "opening_text": "预算16元，能给我更优惠且15分钟内送达的方案吗？",
    }
    r = requests.post(f"{BASE_HTTP}/a2a/dialogue/start", headers=HEADERS, data=json.dumps(body), timeout=15)
    r.raise_for_status()
    data = r.json()
    print(f"[HTTP] start -> session_id={data['session_id']}")
    return data["session_id"]


async def http_client_turn_and_wait(session_id: str, text: str, expected_price: float, round_no: int) -> None:
    body = {
        "session_id": session_id,
        "client_id": CLIENT_ID,
        "text": text,
        "expected_price": expected_price,
    }
    r = requests.post(f"{BASE_HTTP}/a2a/dialogue/client_turn", headers=HEADERS, data=json.dumps(body), timeout=15)
    r.raise_for_status()
    print(f"[HTTP] client_turn round={round_no} -> ok")

    print(f"[WAIT] 等待商家第 {round_no} 轮回复...")
    start_wait = time.time()
    while time.time() - start_wait < 5.0:
        if len(received_turns[round_no]) >= 2:
            print("[WAIT] 收到商家回复 ✓")
            return
        turn_event.clear()
        try:
            await asyncio.wait_for(turn_event.wait(), timeout=1.0)
        except asyncio.TimeoutError:
            pass

    print("[WARN] 等待商家回复超时（可能网络延迟）")


def http_get_dialogue(session_id: str) -> None:
    r = requests.get(f"{BASE_HTTP}/a2a/dialogue/{session_id}", headers=HEADERS, timeout=15)
    r.raise_for_status()
    data = r.json()
    turns = data.get("turns", [])
    print(f"\n[HTTP] 会话完整历史 (共 {len(turns)} 轮):")
    print("=" * 90)
    for turn in turns:
        round_no = turn.get("round", 0)
        sender = turn.get("sender_role", "")
        text = turn.get("text", "")[:70]
        price = turn.get("offered_price") or turn.get("expected_price") or "-"
        hint = turn.get("strategy_hint", "")[:32]
        print(f"Round {round_no} | {sender:8} | 价格:{str(price):>6} | hint:{hint} | {text}")
    print("=" * 90)


def http_close_dialogue(session_id: str) -> None:
    r = requests.post(f"{BASE_HTTP}/a2a/dialogue/{session_id}/close", headers=HEADERS, timeout=15)
    r.raise_for_status()
    print(f"[HTTP] close -> status={r.json()['status']}")


async def main() -> None:
    listener_task = asyncio.create_task(ws_listener())
    await asyncio.sleep(1.5)

    try:
        http_setup_profiles()
        session_id = http_start_dialogue()
        await asyncio.sleep(1.0)

        await http_client_turn_and_wait(session_id, "如果15元可以我现在下单", 15.0, round_no=2)
        await asyncio.sleep(1.0)

        await http_client_turn_and_wait(session_id, "可以加一份小菜吗？", 15.5, round_no=3)
        await asyncio.sleep(1.0)

        http_get_dialogue(session_id)
        http_close_dialogue(session_id)

        print("\n✅ 对话演示完成！")
    finally:
        await asyncio.sleep(0.5)
        listener_task.cancel()
        try:
            await listener_task
        except asyncio.CancelledError:
            pass


if __name__ == "__main__":
    asyncio.run(main())
