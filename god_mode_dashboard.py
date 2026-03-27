"""
Project Claw - 上帝视角监控大屏 (God Mode Dashboard)
用于投资人路演的实时 A2A 谈判可视化系统
"""

import streamlit as st
import pandas as pd
import numpy as np
import pydeck as pdk
import asyncio
import json
import time
from datetime import datetime, timedelta
from collections import deque
import random
from typing import Dict, List, Tuple

# ─── Streamlit 配置 ───
st.set_page_config(
    page_title="Project Claw · 上帝视角",
    page_icon="🦞",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Dark 主题
st.markdown("""
<style>
    [data-testid="stAppViewContainer"] { background-color: #0d0d0f; }
    [data-testid="stSidebar"] { background-color: #1a1a2e; }
    .stMetric { background-color: rgba(255,255,255,0.05); border-radius: 12px; padding: 16px; }
    .metric-label { font-size: 14px; color: rgba(255,255,255,0.55); }
    .metric-value { font-size: 48px; font-weight: 800; color: #30d158; }
    .log-container { background-color: #1a1a2e; border-radius: 12px; padding: 16px; 
                     font-family: 'Monaco', 'Courier New', monospace; font-size: 12px; 
                     max-height: 600px; overflow-y: auto; }
    .log-buyer { color: #5ac8fa; }
    .log-seller { color: #ff9f0a; }
    .log-deal { color: #30d158; font-weight: bold; }
    .log-warn { color: #ff3b5c; }
</style>
""", unsafe_allow_html=True)

# ─── 全局状态 ───
if "logs" not in st.session_state:
    st.session_state.logs = deque(maxlen=200)
if "active_nodes" not in st.session_state:
    st.session_state.active_nodes = 0
if "total_negotiations" not in st.session_state:
    st.session_state.total_negotiations = 0
if "total_savings" not in st.session_state:
    st.session_state.total_savings = 0.0
if "trades_today" not in st.session_state:
    st.session_state.trades_today = []
if "last_update" not in st.session_state:
    st.session_state.last_update = time.time()

# ─── 模拟数据生成器 ───
MERCHANTS = [
    {"id": "box-001", "name": "王记快餐", "lat": 31.1304, "lon": 121.4298, "color": [255, 107, 53]},
    {"id": "box-002", "name": "小杨生煎", "lat": 31.1310, "lon": 121.4305, "color": [255, 59, 92]},
    {"id": "box-003", "name": "鲜得来", "lat": 31.1295, "lon": 121.4290, "color": [48, 209, 88]},
    {"id": "box-004", "name": "大壶春", "lat": 31.1320, "lon": 121.4310, "color": [10, 132, 255]},
    {"id": "box-005", "name": "南翔馄饨", "lat": 31.1300, "lon": 121.4315, "color": [255, 159, 10]},
    {"id": "box-006", "name": "蟹壳黄", "lat": 31.1308, "lon": 121.4285, "color": [175, 82, 222]},
    {"id": "box-007", "name": "绿波廊", "lat": 31.1312, "lon": 121.4300, "color": [0, 199, 190]},
    {"id": "box-008", "name": "龙华素斋", "lat": 31.1305, "lon": 121.4308, "color": [255, 204, 0]},
]

ITEMS = ["牛肉面", "生煎包", "馄饨汤", "红油抄手", "小笼包", "蟹壳黄", "素面", "炸春卷"]

def generate_mock_negotiation() -> Dict:
    """生成模拟谈判数据"""
    merchant = random.choice(MERCHANTS)
    item = random.choice(ITEMS)
    normal_price = random.uniform(12, 28)
    final_price = normal_price * random.uniform(0.85, 0.98)
    savings = normal_price - final_price
    
    return {
        "merchant_id": merchant["id"],
        "merchant_name": merchant["name"],
        "item": item,
        "normal_price": round(normal_price, 2),
        "final_price": round(final_price, 2),
        "savings": round(savings, 2),
        "rounds": random.randint(2, 5),
        "timestamp": datetime.now(),
    }

def add_log(role: str, message: str, log_type: str = "info"):
    """添加日志"""
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    log_entry = {
        "timestamp": timestamp,
        "role": role,
        "message": message,
        "type": log_type,
    }
    st.session_state.logs.append(log_entry)

def format_log_display(log_entry: Dict) -> str:
    """格式化日志显示"""
    ts = log_entry["timestamp"]
    role = log_entry["role"]
    msg = log_entry["message"]
    
    if log_entry["type"] == "deal":
        return f"<span class='log-deal'>[{ts}] ✅ {role}: {msg}</span>"
    elif role == "BUYER_AGENT":
        return f"<span class='log-buyer'>[{ts}] 🧠 {role}: {msg}</span>"
    elif role == "SELLER_AGENT":
        return f"<span class='log-seller'>[{ts}] 🤖 {role}: {msg}</span>"
    elif log_entry["type"] == "warn":
        return f"<span class='log-warn'>[{ts}] ⚠️ {role}: {msg}</span>"
    else:
        return f"[{ts}] {role}: {msg}"

# ─── 页面标题 ───
st.markdown("""
<div style='text-align: center; padding: 20px 0;'>
    <h1 style='font-size: 48px; font-weight: 800; margin: 0;'>🦞 Project Claw</h1>
    <p style='font-size: 18px; color: rgba(255,255,255,0.55); margin: 8px 0;'>
        A2A 智能买手 · 上帝视角监控大屏
    </p>
</div>
""", unsafe_allow_html=True)

# ─── 核心组件 2: 去中心化数据罗盘 ───
st.markdown("### 📊 实时数据罗盘")
col1, col2, col3 = st.columns(3)

with col1:
    # 活跃节点数（模拟跳动）
    active_nodes = random.randint(6, 8)
    st.session_state.active_nodes = active_nodes
    st.markdown(f"""
    <div style='text-align: center; padding: 20px; background: rgba(48,209,88,0.1); border-radius: 12px;'>
        <div class='metric-label'>🟢 活跃龙虾节点</div>
        <div class='metric-value'>{active_nodes}</div>
        <div style='font-size: 12px; color: rgba(255,255,255,0.4); margin-top: 8px;'>上海商圈在线</div>
    </div>
    """, unsafe_allow_html=True)

with col2:
    # 今日谈判总次数
    total_neg = st.session_state.total_negotiations
    st.markdown(f"""
    <div style='text-align: center; padding: 20px; background: rgba(10,132,255,0.1); border-radius: 12px;'>
        <div class='metric-label'>⚡ 今日砍价次数</div>
        <div class='metric-value'>{total_neg}</div>
        <div style='font-size: 12px; color: rgba(255,255,255,0.4); margin-top: 8px;'>A2A 谈判轮次</div>
    </div>
    """, unsafe_allow_html=True)

with col3:
    # 累计为商家夺回的抽成
    total_savings = st.session_state.total_savings
    st.markdown(f"""
    <div style='text-align: center; padding: 20px; background: rgba(255,59,92,0.1); border-radius: 12px;'>
        <div class='metric-label'>💰 累计为商家夺回</div>
        <div class='metric-value'>¥{total_savings:.0f}</div>
        <div style='font-size: 12px; color: rgba(255,255,255,0.4); margin-top: 8px;'>平台抽成节省</div>
    </div>
    """, unsafe_allow_html=True)

st.divider()

# ─── 核心组件 3: 实时地图 ───
st.markdown("### 🗺️ 实时交易地图 (上海徐家汇商圈)")

# 构建地图数据
map_data = []
for merchant in MERCHANTS:
    map_data.append({
        "lat": merchant["lat"],
        "lon": merchant["lon"],
        "name": merchant["name"],
        "color": merchant["color"],
    })

# 添加最近交易的连线
connections = []
if len(st.session_state.trades_today) >= 2:
    # 随机选择最近的几笔交易显示连线
    recent_trades = st.session_state.trades_today[-3:]
    for i, trade in enumerate(recent_trades):
        merchant = next((m for m in MERCHANTS if m["id"] == trade["merchant_id"]), None)
        if merchant:
            # 从中心点到商家的连线
            connections.append({
                "source": [121.4300, 31.1305],  # 徐家汇中心
                "target": [merchant["lon"], merchant["lat"]],
                "color": merchant["color"],
            })

# 构建 pydeck 图层
layers = [
    pdk.Layer(
        "ScatterplotLayer",
        data=pd.DataFrame(map_data),
        get_position=["lon", "lat"],
        get_color="color",
        get_radius=100,
        pickable=True,
    ),
]

# 添加连线图层
if connections:
    line_data = pd.DataFrame(connections)
    layers.append(
        pdk.Layer(
            "LineLayer",
            data=line_data,
            get_source_position="source",
            get_target_position="target",
            get_color="color",
            get_width=3,
            pickable=True,
        )
    )

# 渲染地图
view_state = pdk.ViewState(
    latitude=31.1305,
    longitude=121.4300,
    zoom=15,
    pitch=0,
)

st.pydeck_chart(
    pdk.Deck(
        layers=layers,
        initial_view_state=view_state,
        map_style="mapbox://styles/mapbox/dark-v11",
    ),
    use_container_width=True,
)

st.divider()

# ─── 核心组件 1: A2A 脑机接口日志控制台 ───
st.markdown("### 🧠 A2A 脑机接口 · 实时思考过程")

# 模拟实时数据流
if st.button("🚀 启动模拟谈判流", key="start_sim"):
    with st.spinner("正在生成 A2A 谈判数据流..."):
        for _ in range(5):
            trade = generate_mock_negotiation()
            
            # 模拟 BUYER_AGENT 思考过程
            add_log(
                "BUYER_AGENT",
                f"分析 {trade['item']} 市场价格: ¥{trade['normal_price']:.2f}",
                "info"
            )
            time.sleep(0.3)
            
            add_log(
                "BUYER_AGENT",
                f"目标价格: ¥{trade['final_price']:.2f} (节省 ¥{trade['savings']:.2f})",
                "info"
            )
            time.sleep(0.3)
            
            # 模拟 SELLER_AGENT 思考过程
            add_log(
                "SELLER_AGENT",
                f"[{trade['merchant_name']}] 收到砍价请求，评估利润空间...",
                "info"
            )
            time.sleep(0.3)
            
            add_log(
                "SELLER_AGENT",
                f"[{trade['merchant_name']}] 经过 {trade['rounds']} 轮谈判，同意降价",
                "info"
            )
            time.sleep(0.3)
            
            # 成交
            add_log(
                "SYSTEM",
                f"✅ 成交! {trade['merchant_name']} - {trade['item']} ¥{trade['final_price']:.2f}",
                "deal"
            )
            
            st.session_state.total_negotiations += 1
            st.session_state.total_savings += trade["savings"]
            st.session_state.trades_today.append(trade)
            
            time.sleep(0.5)

# 显示日志控制台
st.markdown('<div class="log-container">', unsafe_allow_html=True)
if st.session_state.logs:
    for log_entry in list(st.session_state.logs)[-50:]:  # 显示最近 50 条
        st.markdown(format_log_display(log_entry), unsafe_allow_html=True)
else:
    st.markdown(
        '<span style="color: rgba(255,255,255,0.3);">等待 A2A 谈判数据流...</span>',
        unsafe_allow_html=True
    )
st.markdown('</div>', unsafe_allow_html=True)

st.divider()

# ─── 底部统计表格 ───
st.markdown("### 📈 今日成交统计")
if st.session_state.trades_today:
    df = pd.DataFrame(st.session_state.trades_today)
    df["timestamp"] = df["timestamp"].dt.strftime("%H:%M:%S")
    df = df[["timestamp", "merchant_name", "item", "normal_price", "final_price", "savings", "rounds"]]
    df.columns = ["时间", "商家", "商品", "原价", "成交价", "节省", "轮数"]
    st.dataframe(df, use_container_width=True, hide_index=True)
else:
    st.info("暂无成交记录，点击上方按钮启动模拟谈判")

# ─── 自动刷新 ───
st.markdown("""
<script>
    setTimeout(function() {
        window.location.reload();
    }, 30000);  // 每 30 秒自动刷新
</script>
""", unsafe_allow_html=True)
