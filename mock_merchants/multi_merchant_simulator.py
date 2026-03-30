"""
Project Claw v14.3 - mock_merchants/multi_merchant_simulator.py
多商家模拟器：同时模拟 7 家虚拟商家在线，无需真实 Android 设备
每家商家有独立菜单、坐标、风格，AI 实时报价
"""
from __future__ import annotations
import asyncio
import json
import logging
import os
import sys
import time
import csv
import requests
import websockets
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))
from shared.claw_protocol import MerchantOffer, TradeRequest, SignalEnvelope, MsgType

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger("claw.mock.multi")

HUB_HTTP  = os.getenv("HUB_HTTP",  "https://project-claw-production.up.railway.app")
HUB_WS    = os.getenv("HUB_WS",   "wss://project-claw-production.up.railway.app")
MERCHANT_KEY = os.getenv("HUB_MERCHANT_KEY", "merchant-shared-key")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")


# ─── 商家定义 ────────────────────────────────────────────────────────────────
@dataclass
class MerchantConfig:
    merchant_id: str
    name: str
    lat: float
    lng: float
    style: str          # AI 报价话术风格
    menu_csv: str       # 相对于项目根目录
    menu: dict = field(default_factory=dict)  # {菜品名: {price, floor, spec, desc}}


MERCHANTS: list[MerchantConfig] = [
    MerchantConfig(
        merchant_id="box-002",
        name="成都麻辣烫",
        lat=31.2310, lng=121.4745,
        style="热情四川老板，说话带川味，喜欢叫客人老铁，强调麻辣鲜香",
        menu_csv="merchants/box-002/menu.csv",
    ),
    MerchantConfig(
        merchant_id="box-003",
        name="广式茶餐厅",
        lat=31.2298, lng=121.4729,
        style="广式茶餐厅，斯文有礼，叫客人靓仔靓女，强调新鲜食材",
        menu_csv="merchants/box-003/menu.csv",
    ),
    MerchantConfig(
        merchant_id="box-004",
        name="家常小炒",
        lat=31.2315, lng=121.4752,
        style="实在家常店，叫客人朋友，强调量大实惠，家的味道",
        menu_csv="merchants/box-004/menu.csv",
    ),
    MerchantConfig(
        merchant_id="box-005",
        name="北方饺子馆",
        lat=31.2289, lng=121.4718,
        style="东北大姐，热情豪爽，叫客人亲，强调手工现包皮薄馅大",
        menu_csv="merchants/box-005/menu.csv",
    ),
    MerchantConfig(
        merchant_id="box-006",
        name="陕西面馆",
        lat=31.2302, lng=121.4740,
        style="陕西老陕，憨厚朴实，叫客人娃，强调正宗古早味地道",
        menu_csv="merchants/box-006/menu.csv",
    ),
    MerchantConfig(
        merchant_id="box-007",
        name="轻食咖啡",
        lat=31.2320, lng=121.4760,
        style="文艺咖啡店，温柔知性，叫客人朋友，强调健康低卡营养均衡",
        menu_csv="merchants/box-007/menu.csv",
    ),
    MerchantConfig(
        merchant_id="box-008",
        name="韩式料理",
        lat=31.2295, lng=121.4725,
        style="韩式料理店，活泼热情，叫客人欧巴欧尼，强调正宗韩国风味",
        menu_csv="merchants/box-008/menu.csv",
    ),
]


# ─── 菜单加载 ────────────────────────────────────────────────────────────────
def load_menu(csv_path: str) -> dict:
    root = Path(__file__).parent.parent
    p = root / csv_path
    menu = {}
    if not p.exists():
        logger.warning(f"菜单文件不存在: {p}")
        return menu
    with open(p, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row["菜品名"].strip()
            menu[name] = {
                "price": float(row["价格"]),
                "floor": float(row["底价"]),
                "spec":  row.get("规格", ""),
                "desc":  row.get("描述", ""),
            }
    return menu


# ─── LLM 报价话术 ─────────────────────────────────────────────────────────────
def llm_reply(demand: str, item_name: str, price: float, style: str, desc: str) -> str:
    if not DEEPSEEK_API_KEY:
        return f"欢迎！{item_name} {price:.0f}元，欢迎光临！"
    try:
        r = requests.post(
            "https://api.deepseek.com/chat/completions",
            json={
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": (
                        f"你是餐厅老板，风格：{style}。"
                        f"菜品：{item_name}，{desc}，报价{price:.0f}元。"
                        "根据顾客需求生成热情简短的报价话术，不超过30字，不要透露底价。"
                    )},
                    {"role": "user", "content": demand},
                ],
                "max_tokens": 50,
                "temperature": 0.8,
            },
            headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"},
            timeout=12,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.warning(f"[LLM] 失败: {e}")
        return f"{item_name} {price:.0f}元，欢迎光临！"


# ─── 菜品匹配 ────────────────────────────────────────────────────────────────
def match_item(menu: dict, item_name: str, demand_text: str) -> Optional[tuple]:
    """关键词匹配，返回 (name, info) 或 None"""
    # 精确匹配
    for name, info in menu.items():
        if item_name in name or name in item_name:
            return name, info
    # 需求文本匹配
    for name, info in menu.items():
        if name in demand_text:
            return name, info
    return None


# ─── 单商家 WebSocket 客户端 ──────────────────────────────────────────────────
async def run_merchant(cfg: MerchantConfig):
    log = logging.getLogger(f"claw.mock.{cfg.merchant_id}")
    cfg.menu = load_menu(cfg.menu_csv)
    log.info(f"[{cfg.name}] 菜单加载 {len(cfg.menu)} 项")

    # 鉴权
    while True:
        try:
            res = requests.post(
                f"{HUB_HTTP}/api/v1/auth/merchant",
                json={"merchant_id": cfg.merchant_id, "key": MERCHANT_KEY},
                timeout=8,
            )
            token = res.json().get("token", "")
            if token:
                log.info(f"[{cfg.name}] 鉴权成功")
                break
        except Exception as e:
            log.warning(f"[{cfg.name}] 鉴权失败: {e}，3秒后重试")
        await asyncio.sleep(3)

    ws_url = (f"{HUB_WS}/ws/merchant/{cfg.merchant_id}"
              f"?token={token}&lat={cfg.lat}&lng={cfg.lng}")

    while True:
        try:
            async with websockets.connect(ws_url, ping_interval=20, ping_timeout=10) as ws:
                log.info(f"[{cfg.name}] ✅ 已连接信令塔")
                async for raw in ws:
                    try:
                        env = SignalEnvelope.model_validate_json(raw)
                    except Exception:
                        continue

                    # 心跳
                    if env.msg_type == MsgType.HEARTBEAT:
                        pong = SignalEnvelope(
                            msg_type=MsgType.HEARTBEAT,
                            sender_id=cfg.merchant_id,
                            payload={"type": "pong", "ts": time.time()},
                        )
                        await ws.send(pong.model_dump_json())
                        continue

                    # 询价广播
                    if env.msg_type == MsgType.INTENT_BROADCAST:
                        req = TradeRequest(**env.payload)
                        asyncio.ensure_future(_handle_request(ws, cfg, req, log))

                    # 成交指令（模拟执行）
                    elif env.msg_type == MsgType.EXECUTE_TRADE:
                        trade = env.payload
                        log.info(f"[{cfg.name}] ⚡ 成交! price={trade.get('final_price')} client={trade.get('client_id')}")
                        # 模拟回执
                        ack = SignalEnvelope(
                            msg_type=MsgType.ACK,
                            sender_id=cfg.merchant_id,
                            payload={
                                "type": "execute_result",
                                "ok": True,
                                "request_id": trade.get("request_id", ""),
                                "client_id": trade.get("client_id", ""),
                                "reason": "",
                            },
                        )
                        await ws.send(ack.model_dump_json())

        except Exception as e:
            log.warning(f"[{cfg.name}] 连接断开: {e}，5秒后重连")
            await asyncio.sleep(5)


async def _handle_request(ws, cfg: MerchantConfig, req: TradeRequest, log):
    """处理单个询价：菜品匹配 → LLM 生成话术 → 回传报价"""
    matched = match_item(cfg.menu, req.item_name, req.demand_text)
    if not matched:
        log.info(f"[{cfg.name}] 无匹配菜品: {req.item_name}，跳过")
        return

    name, info = matched
    floor = info["floor"]
    normal = info["price"]
    final = min(normal, req.max_price)

    if final < floor:
        log.info(f"[{cfg.name}] 低于底价 {final}<{floor}，拒绝")
        return

    # 匹配度计算
    match_score = round(min(100.0, 60.0 + (req.max_price - final) / max(req.max_price, 1) * 40), 1)

    # LLM 话术（在线程池中执行避免阻塞）
    loop = asyncio.get_event_loop()
    reply_text = await loop.run_in_executor(
        None, llm_reply, req.demand_text, name, final, cfg.style, info["desc"]
    )

    import uuid
    offer = MerchantOffer(
        request_id=req.request_id,
        merchant_id=cfg.merchant_id,
        item_name=name,
        final_price=final,
        floor_price=floor,
        reply_text=reply_text,
        match_score=match_score,
        viable=True,
        offer_id=str(uuid.uuid4())[:8],
    )

    env = SignalEnvelope(
        msg_type=MsgType.MERCHANT_OFFER,
        sender_id=cfg.merchant_id,
        payload=offer.model_dump(),
    )
    await ws.send(env.model_dump_json())
    log.info(f"[{cfg.name}] 报价回传 {name} {final}元 score={match_score}")


# ─── 主入口 ──────────────────────────────────────────────────────────────────
async def main():
    # 从环境变量读 DeepSeek Key
    global DEEPSEEK_API_KEY
    if not DEEPSEEK_API_KEY:
        env_file = Path(__file__).parent.parent / "edge_box" / ".env"
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                if line.startswith("DEEPSEEK_API_KEY="):
                    DEEPSEEK_API_KEY = line.split("=", 1)[1].strip()
                    break

    logger.info(f"启动 {len(MERCHANTS)} 家虚拟商家...")
    logger.info(f"Hub: {HUB_HTTP}")
    logger.info(f"DeepSeek Key: {'已配置' if DEEPSEEK_API_KEY else '未配置（使用默认话术）'}")

    await asyncio.gather(*[run_merchant(cfg) for cfg in MERCHANTS])


if __name__ == "__main__":
    asyncio.run(main())
