from __future__ import annotations

import asyncio
import json
import random
import time
from collections import deque
from typing import Any, Deque, Dict, List

import streamlit as st

try:
    from streamlit_lottie import st_lottie
except Exception:  # noqa: BLE001
    st_lottie = None

try:
    import websockets
except Exception:  # noqa: BLE001
    websockets = None

st.set_page_config(page_title="Project Claw · A2A Arena", page_icon="⚔️", layout="wide", initial_sidebar_state="collapsed")

SUCCESS_LOTTIE: Dict[str, Any] = {"v": "5.7.4", "fr": 30, "ip": 0, "op": 90, "w": 1200, "h": 700, "nm": "digital_coin_rain", "ddd": 0, "assets": [], "layers": []}
for idx, x in enumerate(range(80, 1120, 120), start=1):
    SUCCESS_LOTTIE["layers"].append({
        "ddd": 0, "ind": idx, "ty": 4, "nm": f"coin_{idx}", "sr": 1,
        "ks": {"o": {"a": 0, "k": 100}, "r": {"a": 0, "k": 0}, "p": {"a": 1, "k": [{"t": 0, "s": [x, -80, 0], "e": [x + (idx % 3) * 18, 760, 0]}, {"t": 90, "s": [x + (idx % 3) * 18, 760, 0]}]}, "a": {"a": 0, "k": [0, 0, 0]}, "s": {"a": 0, "k": [100, 100, 100]}},
        "ao": 0,
        "shapes": [{"ty": "gr", "it": [{"ty": "el", "p": {"a": 0, "k": [0, 0]}, "s": {"a": 0, "k": [34, 34]}, "nm": "ellipse"}, {"ty": "fl", "c": {"a": 0, "k": [0.98, 0.78, 0.12, 1]}, "o": {"a": 0, "k": 100}, "nm": "fill"}, {"ty": "st", "c": {"a": 0, "k": [1, 0.95, 0.45, 1]}, "o": {"a": 0, "k": 100}, "w": {"a": 0, "k": 2}, "nm": "stroke"}, {"ty": "tr", "p": {"a": 0, "k": [0, 0]}, "a": {"a": 0, "k": [0, 0]}, "s": {"a": 0, "k": [100, 100]}, "r": {"a": 0, "k": 0}, "o": {"a": 0, "k": 100}}], "nm": "coin_group"}],
        "ip": 0, "op": 90, "st": 0, "bm": 0,
    })

BUYER_THOUGHTS = ["分析对方底牌中... 尝试施压。", "识别利润空间，准备继续压价。", "对方让步速度偏慢，切换柔性谈判。", "模拟竞对报价，制造稀缺感。", "预算边界仍安全，继续试探。"]
SELLER_THOUGHTS = ["查阅底价为 12 元... 利润足够，抛出诱饵。", "买方压价强势，先守住最低毛利。", "库存健康，可适度让利换成交。", "检测用户成交意愿上升，准备收口。", "保持掌柜风度，但绝不击穿底线。"]
JUDGE_LINES = ["裁判正在评估双方价格差。", "检测情绪强度与收敛趋势。", "当前谈判仍具继续价值。", "差价已收敛，接近成交阈值。"]


def generate_mock_a2a_events() -> List[Dict[str, Any]]:
    buyer_prices = [14.0, 14.4, 14.8, 15.0]
    seller_prices = [18.0, 16.6, 15.6, 15.0]
    events: List[Dict[str, Any]] = []
    for idx in range(4):
        events.append({"node": "BuyerNode", "thought": BUYER_THOUGHTS[idx % len(BUYER_THOUGHTS)], "action": f"counter_offer:{buyer_prices[idx]:.2f}", "message": f"买手出价提升至 ¥{buyer_prices[idx]:.2f}", "price": buyer_prices[idx], "status": "active", "round": idx + 1})
        events.append({"node": "SellerNode", "thought": SELLER_THOUGHTS[idx % len(SELLER_THOUGHTS)], "action": f"counter_offer:{seller_prices[idx]:.2f}", "message": f"掌柜回击报价 ¥{seller_prices[idx]:.2f}", "price": seller_prices[idx], "status": "active", "round": idx + 1})
        judge_status = "SUCCESS" if idx == 3 else "CONTINUE"
        events.append({"node": "JudgeNode", "thought": JUDGE_LINES[idx % len(JUDGE_LINES)], "action": f"decision:{judge_status}", "message": "交易达成！已绕过大厂抽成！" if judge_status == "SUCCESS" else "裁判判定继续谈判。", "price": seller_prices[idx], "status": judge_status, "round": idx + 1})
    return events


async def _pull_ws_events(url: str, timeout_sec: float = 1.6) -> List[Dict[str, Any]]:
    if not websockets or not url:
        return []
    events: List[Dict[str, Any]] = []
    try:
        async with websockets.connect(url, open_timeout=1, close_timeout=1) as ws:
            started = time.time()
            while time.time() - started < timeout_sec and len(events) < 6:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=0.35)
                except asyncio.TimeoutError:
                    break
                payload = json.loads(raw)
                if isinstance(payload, dict):
                    events.append(payload)
    except Exception:
        return []
    return events


class ArenaDashboardState:
    def __init__(self) -> None:
        self.left_log: Deque[str] = deque(maxlen=10)
        self.right_log: Deque[str] = deque(maxlen=10)
        self.judge_log: Deque[str] = deque(maxlen=6)
        self.price: float = 15.00
        self.countdown: int = 12
        self.turn: int = 1
        self.success: bool = False
        self.feed: List[Dict[str, Any]] = generate_mock_a2a_events()
        self.feed_index: int = 0
        self.last_tick: float = 0.0

    def push_event(self, event: Dict[str, Any]) -> None:
        node = str(event.get("node", ""))
        thought = str(event.get("thought", ""))
        action = str(event.get("action", ""))
        status = str(event.get("status", "")).upper()
        price = event.get("price")
        if price is not None:
            self.price = float(price)
        self.turn = int(event.get("round", self.turn))
        if node == "BuyerNode":
            self.left_log.appendleft(f"{thought} 〔{action}〕")
        elif node == "SellerNode":
            self.right_log.appendleft(f"{thought} 〔{action}〕")
        elif node == "JudgeNode":
            self.judge_log.appendleft(str(event.get("message", thought)))
            if status == "SUCCESS":
                self.success = True
        self.countdown = max(1, self.countdown - 2)

    def tick_mock(self) -> None:
        now = time.time()
        if now - self.last_tick < 0.9:
            return
        self.last_tick = now
        if self.feed_index >= len(self.feed):
            self.feed_index = 0
            self.success = False
            self.countdown = 12
            self.left_log.clear()
            self.right_log.clear()
            self.judge_log.clear()
        event = self.feed[self.feed_index]
        self.feed_index += 1
        self.push_event(event)


if "arena_dashboard_state" not in st.session_state:
    st.session_state.arena_dashboard_state = ArenaDashboardState()
state: ArenaDashboardState = st.session_state.arena_dashboard_state

st.markdown("""
<style>
.stApp { background: radial-gradient(circle at top, rgba(0,212,255,0.12), transparent 35%), radial-gradient(circle at bottom right, rgba(255,136,0,0.16), transparent 28%), #0e1117; color: #e6edf3; }
.main-title { text-align:center; font-size: 58px; font-weight: 900; letter-spacing: 0.18em; color:#d9f7ff; text-shadow: 0 0 24px rgba(0,212,255,.32); margin-bottom: .2rem; }
.sub-title { text-align:center; color:#7f8ea3; letter-spacing:.26em; margin-bottom: 1.6rem; }
.arena-card { background: linear-gradient(180deg, rgba(18,24,38,.96), rgba(12,16,26,.96)); border:1px solid rgba(90,110,140,.24); border-radius:22px; padding:18px 18px 14px 18px; min-height: 620px; box-shadow: 0 18px 50px rgba(0,0,0,.35); }
.avatar { width:108px; height:108px; border-radius:50%; display:flex; align-items:center; justify-content:center; margin: 8px auto 12px auto; font-size:48px; font-weight:800; }
.avatar.buyer { color:#8be9ff; background: radial-gradient(circle, rgba(0,212,255,.24), rgba(0,212,255,.07)); box-shadow: 0 0 22px rgba(0,212,255,.65), inset 0 0 28px rgba(0,212,255,.2); border:1px solid rgba(0,212,255,.55); }
.avatar.seller { color:#ffc27a; background: radial-gradient(circle, rgba(255,145,0,.24), rgba(255,145,0,.07)); box-shadow: 0 0 22px rgba(255,145,0,.55), inset 0 0 28px rgba(255,145,0,.2); border:1px solid rgba(255,145,0,.45); }
.lane-title { text-align:center; font-size: 24px; font-weight: 800; margin-bottom: 10px; }
.lane-title.buyer { color:#68e1fd; }
.lane-title.seller { color:#ffae57; }
.thought-box { background: rgba(8,12,20,.78); border-radius: 16px; padding: 12px 14px; margin-bottom: 10px; font-size: 15px; line-height: 1.55; border-left: 4px solid #4cc9f0; }
.thought-box.seller { border-left-color: #ff9e45; }
.arena-center { text-align:center; display:flex; flex-direction:column; justify-content:center; min-height:620px; }
.judge-ring { width: 240px; height:240px; border-radius:50%; margin:0 auto 20px auto; border:1px solid rgba(145,130,255,.4); box-shadow: 0 0 42px rgba(120,96,255,.28), inset 0 0 38px rgba(120,96,255,.12); display:flex; align-items:center; justify-content:center; background: radial-gradient(circle, rgba(110,94,255,.14), rgba(12,16,26,.12)); }
.price { font-size: 68px; font-weight: 900; color:#ffe082; text-shadow:0 0 22px rgba(255,224,130,.28); }
.judge-title { color:#b7b0ff; font-size: 24px; font-weight: 800; letter-spacing: .16em; }
.judge-feed { margin-top: 16px; text-align:left; background: rgba(10,14,22,.78); border: 1px solid rgba(110,96,255,.25); border-radius: 16px; padding: 12px 14px; }
.judge-row { color:#c7cbff; font-size:14px; margin:7px 0; }
.success-banner { position:fixed; inset: 0; display:flex; align-items:center; justify-content:center; pointer-events:none; z-index:999; }
.success-text { padding: 28px 44px; border-radius: 24px; background: rgba(11,17,26,.78); border:1px solid rgba(255,214,94,.58); color:#ffe082; font-size: 42px; font-weight: 900; text-shadow: 0 0 26px rgba(255,214,94,.45); box-shadow: 0 0 80px rgba(255,214,94,.22); }
.tiny-note { color:#75829a; font-size: 12px; text-align:center; margin-top:6px; }
</style>
""", unsafe_allow_html=True)

mode = st.sidebar.selectbox("数据源", ["Mock Demo", "Live WebSocket"], index=0)
ws_url = st.sidebar.text_input("WebSocket URL", value="ws://127.0.0.1:8765/ws/a2a/arena/demo")
auto_play = st.sidebar.toggle("自动演示", value=True)

if mode == "Live WebSocket" and ws_url:
    live_events = asyncio.run(_pull_ws_events(ws_url))
    for event in live_events:
        payload = event.get("payload", event) if isinstance(event, dict) else {}
        state.push_event(payload)
elif auto_play:
    state.tick_mock()

st.markdown('<div class="main-title">PROJECT CLAW · A2A ARENA</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-title">CYBERPUNK NEGOTIATION SHOWCASE · BUYER vs SELLER · JUDGE CORE</div>', unsafe_allow_html=True)

left, center, right = st.columns([1.05, 1.2, 1.05])

with left:
    st.markdown('<div class="arena-card">', unsafe_allow_html=True)
    st.markdown('<div class="avatar buyer">C</div>', unsafe_allow_html=True)
    st.markdown('<div class="lane-title buyer">C端买手</div>', unsafe_allow_html=True)
    for line in list(state.left_log) or ["等待战斗开始... 正在扫描掌柜弱点。"]:
        st.markdown(f'<div class="thought-box">{line}</div>', unsafe_allow_html=True)
    st.markdown('<div class="tiny-note">蓝光脑回路 · 实时打印买手内心独白</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

with center:
    st.markdown('<div class="arena-card arena-center">', unsafe_allow_html=True)
    st.markdown('<div class="judge-title">判 决 擂 台</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="judge-ring"><div class="price">¥ {state.price:.2f}</div></div>', unsafe_allow_html=True)
    st.progress(min(max((12 - state.countdown) / 12, 0.0), 1.0), text=f'第 {state.turn} 回合收敛进度 · 倒计时 {state.countdown}s')
    st.markdown('<div class="judge-feed">', unsafe_allow_html=True)
    for line in list(state.judge_log) or ["裁判核心加载中... 准备接收双方论证。"]:
        st.markdown(f'<div class="judge-row">⚖️ {line}</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)
    st.markdown('<div class="tiny-note">跳动价格 + 回合进度条 + JudgeNode 仲裁轨迹</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

with right:
    st.markdown('<div class="arena-card">', unsafe_allow_html=True)
    st.markdown('<div class="avatar seller">B</div>', unsafe_allow_html=True)
    st.markdown('<div class="lane-title seller">B端掌柜</div>', unsafe_allow_html=True)
    for line in list(state.right_log) or ["掌柜静候来价... 正在盘算库存与利润。"]:
        st.markdown(f'<div class="thought-box seller">{line}</div>', unsafe_allow_html=True)
    st.markdown('<div class="tiny-note">橙光掌柜 · 实时打印商家内心独白</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

if state.success:
    if st_lottie is not None:
        st_lottie(SUCCESS_LOTTIE, speed=1, loop=True, height=320, key=f"success_{state.turn}")
    st.markdown('<div class="success-banner"><div class="success-text">交易达成！已绕过大厂抽成！</div></div>', unsafe_allow_html=True)

st.code("""def generate_mock_a2a_events():
    buyer_prices = [14.0, 14.4, 14.8, 15.0]
    seller_prices = [18.0, 16.6, 15.6, 15.0]
    # 依次产出 BuyerNode / SellerNode / JudgeNode 事件
    # 最后一轮 JudgeNode 发出 status='SUCCESS'
""", language="python")

st.markdown("""
<meta http-equiv="refresh" content="1.1">
<div style="text-align:center;color:#66758d;font-size:12px;margin-top:14px;">
    Demo 自动刷新中 · Mock 模式可离线跑满整场双 AI 吵架动画
</div>
""", unsafe_allow_html=True)
