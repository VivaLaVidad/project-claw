"""
Project Claw v14.3 - mock_client/c_end_simulator.py
【C端模拟器】CLI 测试脚本

改进：自动通过 REST 换取 JWT token，再带 token 连接 WS

用法：
  python mock_client/c_end_simulator.py --url http://127.0.0.1:8765 --item 牛肉面 --max 15
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.claw_protocol import (
    MsgType, SignalEnvelope,
    TradeRequest, ExecuteTrade, OfferBundle, MerchantOffer,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("claw.mock_client")


def get_token(http_base: str, client_id: str) -> str:
    """通过 REST 换取 JWT client token"""
    url = http_base.rstrip("/") + "/api/v1/auth/client"
    data = json.dumps({"client_id": client_id}).encode()
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            body = json.loads(resp.read())
            token = body.get("token", "")
            logger.info(f"[Auth] Token 获取成功 client_id={client_id}")
            return token
    except Exception as e:
        logger.error(f"[Auth] Token 获取失败: {e}")
        return ""


async def simulate(
    http_base: str,
    client_id: str,
    item_name: str,
    max_price: float,
    auto_accept: bool = True,
):
    import websockets

    # 1. 换 token
    token = get_token(http_base, client_id)
    if not token:
        print("❌ 无法获取 token，请确认 Hub 已启动")
        return

    # 2. 构造 WS URL（ws:// 替换 http://）
    ws_base = http_base.replace("https://", "wss://").replace("http://", "ws://")
    ws_url = f"{ws_base.rstrip('/')}/ws/client/{client_id}?token={token}"
    logger.info(f"连接信令塔: {ws_url.split('?')[0]}")

    async with websockets.connect(ws_url, open_timeout=10) as ws:
        logger.info("✅ 已连接")

        # 3. 构造 TradeRequest
        req = TradeRequest(
            client_id=client_id,
            item_name=item_name,
            demand_text=f"我要{item_name}，{max_price}元以内",
            max_price=max_price,
            timeout_sec=8.0,
        )
        env = SignalEnvelope.wrap(MsgType.TRADE_REQUEST, client_id, req)

        print("\n" + "=" * 60)
        print(f"发送询价: {req.demand_text}")
        print(f"  request_id = {req.request_id}")
        print(f"  max_price  = {req.max_price} 元")
        print("=" * 60)

        await ws.send(env.model_dump_json())
        logger.info("TradeRequest 已发送，等待商家报价...")

        # 4. 等待 OfferBundle
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=20.0)
        except asyncio.TimeoutError:
            print("\n❌ 等待超时，无商家响应")
            return

        resp_env = SignalEnvelope.model_validate_json(raw)
        if resp_env.msg_type != MsgType.OFFER_BUNDLE:
            print(f"\n⚠️ 收到非预期消息: {resp_env.msg_type} payload={resp_env.payload}")
            return

        bundle = OfferBundle(**resp_env.payload)

        print(f"\n{'='*60}")
        print(f"收到报价汇总 (request_id={bundle.request_id})")
        print(f"  在线商家: {bundle.total_merchants}  已响应: {bundle.responded}")
        print(f"  有效报价: {len(bundle.offers)}  耗时: {bundle.elapsed_ms:.0f}ms")
        print(f"{'='*60}")

        if not bundle.offers:
            print("暂无商家报价（检查 B端菜单或预算是否过低）")
            return

        for i, offer in enumerate(bundle.offers):
            print(
                f"\n  [{i+1}] 商家: {offer.merchant_id}\n"
                f"      商品: {offer.item_name}\n"
                f"      报价: {offer.final_price} 元\n"
                f"      话术: {offer.reply_text}\n"
                f"      匹配度: {offer.match_score:.1f}%"
            )

        if not auto_accept:
            choice = input("\n输入报价编号确认 (或 q 退出): ").strip()
            if choice == "q" or not choice.isdigit():
                return
            idx = int(choice) - 1
        else:
            idx = 0
            print("\n[自动模式] 选择第 1 个报价")

        if idx < 0 or idx >= len(bundle.offers):
            print("无效选择")
            return

        selected: MerchantOffer = bundle.offers[idx]

        # 5. 发送 ExecuteTrade
        trade = ExecuteTrade(
            request_id=bundle.request_id,
            offer_id=selected.offer_id,
            merchant_id=selected.merchant_id,
            client_id=client_id,
            final_price=selected.final_price,
        )
        trade_env = SignalEnvelope.wrap(MsgType.EXECUTE_TRADE, client_id, trade)
        await ws.send(trade_env.model_dump_json())

        print(f"\n✅ ExecuteTrade 已发送!")
        print(f"   商家: {selected.merchant_id}")
        print(f"   金额: {selected.final_price} 元")
        print(f"   话术: {selected.reply_text}")

        # 6. 等待 Hub ACK / ERROR
        try:
            raw2 = await asyncio.wait_for(ws.recv(), timeout=10.0)
            env2 = SignalEnvelope.model_validate_json(raw2)
            if env2.msg_type == MsgType.ACK:
                print("\n✅ Hub ACK: 成交指令已被接收并执行")
                print(json.dumps(env2.payload, ensure_ascii=False, indent=2))
            elif env2.msg_type == MsgType.ERROR:
                print("\n❌ Hub ERROR: 成交指令被拒绝")
                print(json.dumps(env2.payload, ensure_ascii=False, indent=2))
            else:
                print(f"\n⚠️ 收到额外消息: {env2.msg_type}")
        except asyncio.TimeoutError:
            print("\n⚠️ 未收到 Hub ACK（商家离线或网络延迟）")

        # 7. 等待 B端物理执行回执（如果 B端连接了设备）
        try:
            raw3 = await asyncio.wait_for(ws.recv(), timeout=8.0)
            env3 = SignalEnvelope.model_validate_json(raw3)
            if env3.msg_type == MsgType.ACK and env3.payload.get("type") == "execute_result":
                ok = env3.payload.get("ok", False)
                reason = env3.payload.get("reason", "")
                if ok:
                    print("\n✅ B端设备执行成功（微信消息已发送）")
                else:
                    print(f"\n⚠️ B端设备执行结果: {reason}（无物理设备时为正常）")
        except asyncio.TimeoutError:
            print("\n（未收到 B端设备回执，无 Android 设备时属正常）")

        print("\n===== 测试完成 =====")


def main():
    parser = argparse.ArgumentParser(description="Project Claw C端模拟器 v14.3")
    parser.add_argument("--url",  default="http://127.0.0.1:8765", help="Hub HTTP 地址")
    parser.add_argument("--id",   default="sim-client-001",        help="C端 ID")
    parser.add_argument("--item", default="牛肉面",                  help="商品名")
    parser.add_argument("--max",  default=15.0, type=float,         help="最高价格")
    parser.add_argument("--manual", action="store_true",            help="手动选择报价")
    args = parser.parse_args()

    asyncio.run(simulate(
        http_base=args.url,
        client_id=args.id,
        item_name=args.item,
        max_price=args.max,
        auto_accept=not args.manual,
    ))


if __name__ == "__main__":
    main()
