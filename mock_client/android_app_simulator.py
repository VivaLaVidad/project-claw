from __future__ import annotations

import asyncio
import json
import os

import websockets


async def main():
    ws_base = os.getenv("HUB_WS_BASE", "ws://127.0.0.1:8765")
    merchant_id = os.getenv("MERCHANT_ID", "box-001")
    token = os.getenv("MERCHANT_TOKEN", "")

    if not token:
        raise RuntimeError("MERCHANT_TOKEN is required")

    url = f"{ws_base}/ws/android/{merchant_id}?token={token}"
    print(f"[手机端模拟] connecting: {url}")

    async with websockets.connect(url, max_size=2**22) as ws:
        print("[手机端模拟] 已连接，等待 ActionCommand...")
        while True:
            raw = await ws.recv()
            cmd = json.loads(raw)
            content = cmd.get("content", "")
            print(f"[手机端物理执行]: 正在打开微信输入 -> {content}")

            ack = {
                "type": "ACTION_ACK",
                "command_id": cmd.get("command_id"),
                "merchant_id": merchant_id,
                "ok": True,
            }
            await ws.send(json.dumps(ack, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
