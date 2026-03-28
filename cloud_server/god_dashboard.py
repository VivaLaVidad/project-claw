"""
god_dashboard.py - Project Claw 融资路演上帝视角大屏
使用 Streamlit 展示实时交易数据、AI 谈判过程、物理拓扑
"""

import streamlit as st
import pandas as pd
import pydeck as pdk
import asyncio
import json
import time
from datetime import datetime, timedelta
from collections import deque
import random

# ═══════════════════════════════════════════════════════════════
# 页面配置
# ═══════════════════════════════════════════════════════════════

st.set_page_config(
    page_title="Project Claw - 上帝视角",
    page_icon="🦞",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# 暗黑模式主题
st.markdown("""
    <style>
        :root {
            --primary-color: #00ff41;
            --secondary-color: #ff006e;
            --background-color: #0a0e27;
            --surface-color: #1a1f3a;
        }
        
        body {
            background-color: #0a0e27;
            color: #ffffff;
        }
        
        .metric-card {
            background: linear-gradient(135deg, rgba(0, 255, 65, 0.1), rgba(255, 0, 110, 0.1));
            backdrop-filter: blur(10px);
            border: 1px solid rgba(0, 255, 65, 0.2);
            border-radius: 12px;
            padding: 20px;
            text-align: center;
        }
        
        .metric-value {
            font-size: 48px;
            font-weight: 700;
            color: #00ff41;
            text-shadow: 0 0 20px rgba(0, 255, 65, 0.5);
        }
        
        .metric-label {
            font-size: 14px;
            color: #a0a0a0;
            margin-top: 8px;
        }
        
        .console-log {
            background: #0f1428;
            border: 1px solid rgba(0, 255, 65, 0.2);
            border-radius: 8px;
            padding: 16px;
            font-family: 'SF Mono', Monaco, monospace;
            font-size: 12px;
            max-height: 600px;
            overflow-y: auto;
            color: #00ff41;
        }
        
        .log-entry {
            margin: 4px 0;
            padding: 4px 0;
            border-left: 2px solid #00ff41;
            padding-left: 8px;
        }
        
        .log-entry.buyer {
            color: #00d4ff;
            border-left-color: #00d4ff;
        }
        
        .log-entry.seller {
            color: #ff9500;
            border-left-color: #ff9500;
        }
        
        .log-entry.match {
            color: #00ff41;
            border-left-color: #00ff41;
            font-weight: 700;
        }
    </style>
""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════
# 数据模拟
# ═══════════════════════════════════════════════════════════════

class DashboardState:
    """仪表板状态管理"""
    
    def __init__(self):
        self.online_boxes = 0
        self.saved_amount = 0.0
        self.avg_latency = 0.0
        self.logs = deque(maxlen=100)
        self.trades = []
        self.last_update = time.time()
    
    def add_log(self, message: str, log_type: str = "info"):
        """添加日志"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = {
            'timestamp': timestamp,
            'message': message,
            'type': log_type,
            'time': time.time()
        }
        self.logs.append(log_entry)
    
    def add_trade(self, trade_data: dict):
        """添加交易"""
        self.trades.append(trade_data)
        if len(self.trades) > 50:
            self.trades.pop(0)

# 初始化状态
if 'dashboard_state' not in st.session_state:
    st.session_state.dashboard_state = DashboardState()

state = st.session_state.dashboard_state

# ═══════════════════════════════════════════════════════════════
# 页面标题
# ═══════════════════════════════════════════════════════════════

st.markdown("""
    <div style="text-align: center; margin-bottom: 30px;">
        <h1 style="color: #00ff41; font-size: 48px; margin: 0;">🦞 Project Claw</h1>
        <p style="color: #a0a0a0; font-size: 18px; margin: 10px 0;">AI 驱动的极速砍价系统 - 融资路演上帝视角</p>
        <p style="color: #ff006e; font-size: 14px;">实时交易监控 | 智能谈判展示 | 物理拓扑可视化</p>
    </div>
""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════
# 顶部指标阵列
# ═══════════════════════════════════════════════════════════════

st.markdown("### 📊 实时指标")

col1, col2, col3 = st.columns(3)

# 模拟数据更新
state.online_boxes = random.randint(150, 250)
state.saved_amount = random.uniform(50000, 150000)
state.avg_latency = random.uniform(80, 200)

with col1:
    st.metric(
        label="🟢 全网在线黑盒子数",
        value=f"{state.online_boxes}",
        delta=f"+{random.randint(1, 10)}",
        delta_color="normal"
    )

with col2:
    st.metric(
        label="💰 今日拦截大厂抽成金额",
        value=f"¥{state.saved_amount:,.0f}",
        delta=f"+¥{random.uniform(1000, 5000):,.0f}",
        delta_color="normal"
    )

with col3:
    st.metric(
        label="⚡ A2A 撮合平均延迟",
        value=f"{state.avg_latency:.0f}ms",
        delta=f"-{random.uniform(5, 20):.0f}ms",
        delta_color="inverse"
    )

st.divider()

# ═══════════════════════════════════════════════════════════════
# 中心流数据瀑布 + 右侧物理拓扑
# ═══════════════════════════════════════════════════════════════

col_console, col_map = st.columns([1.2, 1])

# ─────────────────────────────────────────────────────────────
# 左侧：实时谈判日志
# ─────────────────────────────────────────────────────────────

with col_console:
    st.markdown("### 📡 实时谈判明文")
    
    # 模拟谈判日志
    sample_logs = [
        ("🔵 买手 Agent", "发起意图: 商品=龙虾, 预算=¥15.0", "buyer"),
        ("🟠 商家 Agent", "收到意图, 初始报价=¥18.0", "seller"),
        ("🔵 买手 Agent", "分析: 预算差距 20%, 启动谈判", "buyer"),
        ("🟠 商家 Agent", "评估: 客户信用度 95%, 可让步", "seller"),
        ("🔵 买手 Agent", "反报价: ¥14.5, 理由: 市场均价", "buyer"),
        ("🟠 商家 Agent", "考虑中... 成本 ¥12.0, 利润空间", "seller"),
        ("🔵 买手 Agent", "最终报价: ¥13.5, 即时成交", "buyer"),
        ("🟠 商家 Agent", "接受! 成交价 ¥13.5", "seller"),
        ("✅ 系统", "MATCH_SUCCESS: 交易已撮合", "match"),
    ]
    
    # 添加日志到状态
    for agent, message, log_type in sample_logs:
        state.add_log(f"{agent}: {message}", log_type)
    
    # 显示日志
    log_html = '<div class="console-log">'
    for log in list(state.logs)[-20:]:
        log_class = f"log-entry {log['type']}"
        log_html += f'<div class="{log_class}">[{log["timestamp"]}] {log["message"]}</div>'
    log_html += '</div>'
    
    st.markdown(log_html, unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────
# 右侧：3D 地图拓扑
# ─────────────────────────────────────────────────────────────

with col_map:
    st.markdown("### 🗺️ 物理拓扑")
    
    # 上海市中心坐标
    shanghai_center = [121.4737, 31.2304]
    
    # 生成随机交易点
    trades_data = []
    for i in range(5):
        buyer_lat = shanghai_center[1] + random.uniform(-0.1, 0.1)
        buyer_lon = shanghai_center[0] + random.uniform(-0.1, 0.1)
        seller_lat = shanghai_center[1] + random.uniform(-0.1, 0.1)
        seller_lon = shanghai_center[0] + random.uniform(-0.1, 0.1)
        
        trades_data.append({
            'buyer': [buyer_lon, buyer_lat],
            'seller': [seller_lon, seller_lat],
            'amount': random.uniform(10, 50),
            'status': 'matched'
        })
    
    # 创建飞线数据
    arc_data = []
    for trade in trades_data:
        arc_data.append({
            'source': trade['buyer'],
            'target': trade['seller'],
            'amount': trade['amount']
        })
    
    # 创建 pydeck 图层
    arc_layer = pdk.Layer(
        'ArcLayer',
        data=pd.DataFrame(arc_data),
        get_source_position='source',
        get_target_position='target',
        get_source_color=[0, 255, 65],  # 荧光绿
        get_target_color=[255, 0, 110],  # 电光紫
        get_width=3,
        get_tilt=45,
        pickable=True,
        auto_highlight=True,
    )
    
    # 创建散点层（交易点）
    scatter_data = []
    for trade in trades_data:
        scatter_data.append({'position': trade['buyer'], 'type': 'buyer'})
        scatter_data.append({'position': trade['seller'], 'type': 'seller'})
    
    scatter_layer = pdk.Layer(
        'ScatterplotLayer',
        data=pd.DataFrame(scatter_data),
        get_position='position',
        get_fill_color='[0, 255, 65]',
        get_radius=500,
        pickable=True,
    )
    
    # 创建地图
    view_state = pdk.ViewState(
        longitude=shanghai_center[0],
        latitude=shanghai_center[1],
        zoom=11,
        pitch=45,
        bearing=0
    )
    
    map_style = "mapbox://styles/mapbox/dark-v11"
    
    r = pdk.Deck(
        layers=[arc_layer, scatter_layer],
        initial_view_state=view_state,
        map_style=map_style,
        tooltip={"text": "交易撮合中..."}
    )
    
    st.pydeck_chart(r, use_container_width=True)

st.divider()

# ═══════════════════════════════════════════════════════════════
# 底部：交易统计
# ═══════════════════════════════════════════════════════════════

st.markdown("### 📈 交易统计")

stat_col1, stat_col2, stat_col3, stat_col4 = st.columns(4)

with stat_col1:
    st.metric("今日交易数", f"{random.randint(500, 1000)}", "+50")

with stat_col2:
    st.metric("成功率", f"{random.uniform(95, 99):.1f}%", "+0.5%")

with stat_col3:
    st.metric("平均节省", f"¥{random.uniform(2, 5):.2f}", "+¥0.50")

with stat_col4:
    st.metric("用户满意度", f"{random.uniform(4.5, 5.0):.1f}/5.0", "+0.1")

# ═══════════════════════════════════════════════════════════════
# 自动刷新
# ═══════════════════════════════════════════════════════════════

st.markdown("""
    <script>
        // 每 3 秒自动刷新一次
        setTimeout(function() {
            window.location.reload();
        }, 3000);
    </script>
""", unsafe_allow_html=True)

# 页脚
st.markdown("""
    <div style="text-align: center; margin-top: 40px; padding-top: 20px; border-top: 1px solid rgba(0, 255, 65, 0.1);">
        <p style="color: #a0a0a0; font-size: 12px;">
            Project Claw © 2026 | 融资路演上帝视角 | 实时数据更新中...
        </p>
    </div>
""", unsafe_allow_html=True)
