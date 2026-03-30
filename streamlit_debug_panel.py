"""
Project Claw MiniApp 调试面板
支持本地 Streamlit 调试 + Railway 生产监控
"""

import streamlit as st
import requests
import json
from datetime import datetime
import time

st.set_page_config(
    page_title="Project Claw MiniApp 调试面板",
    page_icon="🦞",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 自定义样式
st.markdown("""
<style>
    .main {
        background: linear-gradient(135deg, #0a0e27 0%, #1a1a3e 100%);
        color: #ffffff;
    }
    .stMetric {
        background: rgba(0, 255, 65, 0.1);
        border: 1px solid rgba(0, 255, 65, 0.3);
        border-radius: 12px;
        padding: 16px;
    }
</style>
""", unsafe_allow_html=True)

# 侧边栏配置
st.sidebar.markdown("## ⚙️ 环境配置")
env = st.sidebar.radio(
    "选择环境",
    ["🏠 本地调试", "☁️ Railway 生产"],
    index=0
)

if env == "🏠 本地调试":
    BASE_URL = "http://127.0.0.1:8765"
    st.sidebar.info("✓ 本地调试模式\n地址: http://127.0.0.1:8765")
else:
    BASE_URL = "https://project-claw-production.up.railway.app"
    st.sidebar.info("✓ Railway 生产模式\n地址: https://project-claw-production.up.railway.app")

# 主标题
st.markdown("""
# 🦞 Project Claw MiniApp 调试面板
**智能询价系统 - 极客风范完善版**
""")

# 标签页
tab1, tab2, tab3, tab4 = st.tabs(["🏥 健康检查", "📊 系统状态", "🧪 API 测试", "📋 配置管理"])

# ─── 标签页 1：健康检查 ───
with tab1:
    st.subheader("后端服务健康检查")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("🔍 检查 /health", use_container_width=True):
            try:
                resp = requests.get(f"{BASE_URL}/health", timeout=5)
                if resp.status_code == 200:
                    data = resp.json()
                    st.success("✅ 服务正常")
                    st.json(data)
                else:
                    st.error(f"❌ 状态码: {resp.status_code}")
            except Exception as e:
                st.error(f"❌ 连接失败: {str(e)}")
    
    with col2:
        if st.button("🏪 检查在线商家", use_container_width=True):
            try:
                resp = requests.get(f"{BASE_URL}/api/v1/merchants/online", timeout=5)
                if resp.status_code == 200:
                    data = resp.json()
                    st.success(f"✅ 在线商家: {data.get('online_merchants', 0)}")
                    st.json(data)
                else:
                    st.warning(f"⚠️ 状态码: {resp.status_code}")
            except Exception as e:
                st.error(f"❌ 连接失败: {str(e)}")

# ─── 标签页 2：系统状态 ───
with tab2:
    st.subheader("系统实时状态")
    
    col1, col2, col3, col4 = st.columns(4)
    
    try:
        resp = requests.get(f"{BASE_URL}/health", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            
            with col1:
                st.metric("🟢 服务状态", "正常" if data.get("status") == "ok" else "异常")
            
            with col2:
                st.metric("🏪 在线商家", data.get("merchants", 0))
            
            with col3:
                st.metric("⏰ 时间戳", datetime.fromtimestamp(data.get("ts", 0)).strftime("%H:%M:%S"))
            
            with col4:
                st.metric("🌐 环境", "本地" if "127.0.0.1" in BASE_URL else "Railway")
    except:
        st.error("❌ 无法连接后端")

# ─── 标签页 3：API 测试 ───
with tab3:
    st.subheader("API 端点测试")
    
    api_endpoint = st.selectbox(
        "选择端点",
        [
            "/health",
            "/api/v1/merchants/online",
            "/api/v1/auth/client (POST)",
        ]
    )
    
    if api_endpoint == "/api/v1/auth/client (POST)":
        st.write("**请求体:**")
        client_id = st.text_input("client_id", value="test-client-001")
        
        if st.button("发送请求", use_container_width=True):
            try:
                resp = requests.post(
                    f"{BASE_URL}/api/v1/auth/client",
                    json={"client_id": client_id},
                    timeout=5
                )
                st.write(f"**状态码:** {resp.status_code}")
                st.json(resp.json())
            except Exception as e:
                st.error(f"❌ 请求失败: {str(e)}")
    else:
        if st.button("发送请求", use_container_width=True):
            try:
                resp = requests.get(f"{BASE_URL}{api_endpoint}", timeout=5)
                st.write(f"**状态码:** {resp.status_code}")
                st.json(resp.json())
            except Exception as e:
                st.error(f"❌ 请求失败: {str(e)}")

# ─── 标签页 4：配置管理 ───
with tab4:
    st.subheader("小程序配置")
    
    st.write("### 📝 当前配置")
    
    config_info = {
        "环境": "本地调试" if "127.0.0.1" in BASE_URL else "Railway 生产",
        "后端地址": BASE_URL,
        "小程序目录": "d:\\桌面\\Project Claw\\mini_program_app",
        "AppID": "wx1f7d608c84f6da6d",
        "开发模式": "小程序",
        "后端服务": "不使用云服务",
    }
    
    for key, value in config_info.items():
        st.write(f"**{key}:** `{value}`")
    
    st.divider()
    
    st.write("### 🚀 快速启动")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.write("**本地调试:**")
        st.code("""
# 1. 运行启动脚本
START_MINIAPP_LOCAL.bat

# 2. 微信开发者工具
# - 导入: d:\\桌面\\Project Claw\\mini_program_app
# - 详情 → 本地设置 → 勾选"不校验合法域名"
# - 清缓存 + 重新编译
        """, language="bash")
    
    with col2:
        st.write("**Railway 生产:**")
        st.code("""
# 1. 推送代码到 GitHub
git add .
git commit -m "Update signaling_hub"
git push

# 2. Railway 自动部署
# - 监听 Procfile 和 railway.toml
# - 约 2-5 分钟完成

# 3. 小程序清缓存重编译
        """, language="bash")

st.divider()

st.markdown("""
---
**Project Claw v14.3** | 极客风范完善版 | 🦞 智能询价系统
""")
