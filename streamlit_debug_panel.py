"""
Project Claw v14.3 - 工业级调试面板
赛博朋克深色系 + 毛玻璃拟态 + 实时监控
"""
import streamlit as st
import requests
import json
import time
from datetime import datetime

st.set_page_config(page_title="Project Claw 控制台", page_icon="🦞", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&family=Rajdhani:wght@500;700&display=swap');
*,body,.stApp{font-family:'JetBrains Mono',monospace!important}
.stApp{background:linear-gradient(135deg,#0a0e27 0%,#0d1117 50%,#0a1628 100%)!important}
[data-testid="stSidebar"]{background:rgba(255,255,255,0.04)!important;backdrop-filter:blur(20px);border-right:1px solid rgba(0,255,65,0.15)}
h1,h2,h3{color:#00ff41!important}
[data-testid="stMetric"]{background:rgba(0,255,65,0.06);border:1px solid rgba(0,255,65,0.2);border-radius:12px;padding:16px}
[data-testid="stMetricValue"]{color:#00ff41!important;font-size:24px!important}
.stButton>button{background:rgba(0,255,65,0.08)!important;border:1px solid rgba(0,255,65,0.4)!important;color:#00ff41!important;border-radius:8px!important;font-weight:700!important;transition:all 0.2s ease!important}
.stButton>button:hover{background:rgba(0,255,65,0.18)!important;box-shadow:0 0 16px rgba(0,255,65,0.35)!important}
.stTabs [data-baseweb="tab-list"]{background:rgba(255,255,255,0.03);border-radius:10px;gap:4px}
.stTabs [aria-selected="true"]{background:rgba(0,255,65,0.12)!important;color:#00ff41!important}
.ok{background:rgba(0,255,65,0.08);border:1px solid rgba(0,255,65,0.4);border-radius:10px;padding:12px 18px;color:#00ff41;margin:8px 0}
.er{background:rgba(255,0,110,0.08);border:1px solid rgba(255,0,110,0.4);border-radius:10px;padding:12px 18px;color:#ff006e;margin:8px 0}
.wn{background:rgba(255,200,0,0.07);border:1px solid rgba(255,200,0,0.35);border-radius:10px;padding:12px 18px;color:#ffc800;margin:8px 0}
.ib{background:rgba(0,180,255,0.07);border:1px solid rgba(0,180,255,0.3);border-radius:10px;padding:12px 18px;color:#00b4ff;margin:8px 0}
</style>
""", unsafe_allow_html=True)

def req(method, url, **kwargs):
    try:
        r = requests.request(method, url, timeout=6, **kwargs)
        return r.status_code, r.json()
    except requests.exceptions.ConnectionError:
        return 0, {"error": "无法连接服务器"}
    except Exception as e:
        return 0, {"error": str(e)}

def ok(msg): return f'<div class="ok">✅ {msg}</div>'
def er(msg): return f'<div class="er">❌ {msg}</div>'
def wn(msg): return f'<div class="wn">⚠️ {msg}</div>'
def ib(msg): return f'<div class="ib">ℹ️ {msg}</div>'

# ─── 侧边栏 ────────────────────────────────────────────
st.sidebar.markdown("""
<div style='text-align:center;padding:12px 0'>
<div style='font-size:32px'>🦞</div>
<div style='font-size:18px;font-weight:700;color:#00ff41;font-family:Rajdhani'>PROJECT CLAW</div>
<div style='font-size:11px;color:#a0a0a0'>v14.3.0 工业控制台</div>
</div>
""", unsafe_allow_html=True)
st.sidebar.divider()

env_choice = st.sidebar.radio("⚙️ 环境", ["🏠 本地", "☁️ Railway"], index=0)
if env_choice == "🏠 本地":
    default_url = "http://127.0.0.1:8765"
else:
    default_url = "https://project-claw-production.up.railway.app"

BASE_URL = st.sidebar.text_input("后端地址", value=default_url).rstrip("/")

code, health = req("GET", f"{BASE_URL}/health")
up = code == 200
if up:
    st.sidebar.markdown(ok("服务在线"), unsafe_allow_html=True)
else:
    st.sidebar.markdown(er("服务离线"), unsafe_allow_html=True)

st.sidebar.divider()
st.sidebar.markdown("""
**快捷命令**
```
# 本地启动
.\\START_MINIAPP_LOCAL.bat

# 调试面板
streamlit run streamlit_debug_panel.py

# 推送代码
git push origin main
```
""")

# ─── 主标题 ────────────────────────────────────────────
st.markdown("""
<div style='display:flex;align-items:center;gap:14px;margin-bottom:8px'>
  <span style='font-size:40px'>🦞</span>
  <div>
    <div style='font-size:28px;font-weight:700;color:#00ff41;font-family:Rajdhani;line-height:1'>PROJECT CLAW 工业控制台</div>
    <div style='font-size:13px;color:#a0a0a0;margin-top:2px'>智能询价系统 v14.3 · A2A 博弈引擎 · 1% 路由费</div>
  </div>
</div>
<div style='height:1px;background:linear-gradient(90deg,#00ff41,transparent);margin-bottom:20px'></div>
""", unsafe_allow_html=True)

# ─── 顶部指标 ──────────────────────────────────────────
_, md = req("GET", f"{BASE_URL}/api/v1/merchants/online")
mc = md.get("online_merchants", 0) if up else 0
ts = health.get("ts", 0)
ts_str = datetime.fromtimestamp(ts).strftime("%H:%M:%S") if ts else "--"

c1,c2,c3,c4,c5 = st.columns(5)
with c1: st.metric("🟢 服务", "在线" if up else "离线")
with c2: st.metric("🏪 在线商家", mc)
with c3: st.metric("🌏 环境", "本地" if "127.0.0.1" in BASE_URL else "Railway")
with c4: st.metric("⏰ 服务时间", ts_str)
with c5: st.metric("🔑 认证", "JWT+DID")

st.divider()

# ─── 标签页 ──────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "🏥 健康诊断", "🧪 API 测试", "💰 财务模拟", "🚀 部署指引", "⚙️ 配置管理"
])

# ═══ TAB1 ════════════════════════════════
with tab1:
    st.subheader("后端服务健康诊断")
    l, r = st.columns(2)
    with l:
        if st.button("🔍 检查 /health", use_container_width=True):
            c, d = req("GET", f"{BASE_URL}/health")
            st.markdown(ok(str(d)) if c==200 else er(str(d)), unsafe_allow_html=True)
        if st.button("🏪 检查在线商家", use_container_width=True):
            c, d = req("GET", f"{BASE_URL}/api/v1/merchants/online")
            msg = f"在线商家：{d.get('online_merchants',0)} 家" if c==200 else d.get('error','')
            st.markdown(ok(msg) if c==200 else er(msg), unsafe_allow_html=True)
        if st.button("🔐 测试 JWT 登录", use_container_width=True):
            c, d = req("POST", f"{BASE_URL}/api/v1/auth/client", json={"code":"debug_test"})
            token_preview = str(d.get('token',''))[:30] + '...' if d.get('token') else str(d)
            st.markdown(ok("JWT: "+token_preview) if c==200 else wn(f"HTTP {c} | "+str(d)), unsafe_allow_html=True)
    with r:
        st.markdown("**📋 全量诊断**")
        for method, path, label in [("GET","/health","引擎心跳"),("GET","/api/v1/merchants/online","商家心跳")]:
            ec, _ = req(method, f"{BASE_URL}{path}")
            color = "#00ff41" if ec==200 else "#ff006e"
            icon  = "✅" if ec==200 else "❌"
            st.markdown(f"<span style='color:{color}'>{icon} {label}</span> `{path}`", unsafe_allow_html=True)
        st.divider()
        st.code(f"BASE_URL = {BASE_URL}\nSTATUS   = {'UP' if up else 'DOWN'}\nMERCHANTS= {mc}")

# ═══ TAB2 ════════════════════════════════
with tab2:
    st.subheader("🧪 自定义 API 测试")
    method_sel = st.selectbox("方法", ["GET","POST","PUT","DELETE"])
    path_sel   = st.text_input("路径", value="/api/v1/merchants/online")
    body_str   = st.text_area("请求体 JSON", value="{}", height=100)
    if st.button("▶ 发送", use_container_width=True):
        try: body = json.loads(body_str)
        except: body = {}
        c, d = req(method_sel, f"{BASE_URL}{path_sel}", json=body if method_sel!="GET" else None)
        st.markdown(f"**HTTP {c}**")
        st.json(d) if c==200 else st.markdown(er(str(d)), unsafe_allow_html=True)

# ═══ TAB3 ════════════════════════════════
with tab3:
    st.subheader("💰 1% 路由费分润模拟器")
    price         = st.slider("订单金额（元）", 5.0, 500.0, 30.0, 0.5)
    platform_rate = st.slider("平台路由费率", 0.005, 0.03, 0.01, 0.001, format="%.3f")
    promoter_rate = st.slider("包工头分润比例", 0.3, 0.8, 0.6, 0.05)
    platform_fee     = round(price * platform_rate, 4)
    promoter_cut     = round(platform_fee * promoter_rate, 4)
    platform_keep    = round(platform_fee - promoter_cut, 4)
    merchant_receive = round(price - platform_fee, 4)
    st.divider()
    a,b,c_c,d_c = st.columns(4)
    with a:   st.metric("💳 用户支付",   f"¥{price}")
    with b:   st.metric("🏪 商家到账",   f"¥{merchant_receive}")
    with c_c: st.metric("🔧 包工头",     f"¥{promoter_cut}")
    with d_c: st.metric("🏦 平台净利",   f"¥{platform_keep}")
    st.divider()
    st.markdown("**📈 投资人沙盘**")
    n_orders = st.number_input("日均成交单数", 100, 100000, 2000, 100)
    avg_p    = st.number_input("平均客单价（元）", 5.0, 500.0, 30.0, 1.0)
    daily_gmv  = n_orders * avg_p
    daily_plat = daily_gmv * platform_rate
    daily_prom = daily_plat * promoter_rate
    daily_net  = daily_plat - daily_prom
    llm_calls  = n_orders * 50
    r1,r2,r3,r4 = st.columns(4)
    with r1: st.metric("日 GMV",       f"¥{daily_gmv:,.0f}")
    with r2: st.metric("日平台收入",   f"¥{daily_plat:,.1f}")
    with r3: st.metric("日净利",       f"¥{daily_net:,.1f}")
    with r4: st.metric("日 LLM 调用",  f"{llm_calls:,} 次")
    st.markdown(ib(f"月 GMV ¥{daily_gmv*30:,.0f} · 月净利 ¥{daily_net*30:,.0f} · 5090 算力护城河"), unsafe_allow_html=True)

# ═══ TAB4 ════════════════════════════════
with tab4:
    st.subheader("🚀 部署操作指引")
    cl, cr = st.columns(2)
    with cl:
        st.markdown("**🏠 本地调试**")
        st.code(".\\START_MINIAPP_LOCAL.bat", language="bash")
        st.markdown(ib("启动后：微信开发者工具勾选'不校验合法域名'，清缓存重编译"), unsafe_allow_html=True)
    with cr:
        st.markdown("**☁️ Railway 生产**")
        st.code("git push origin main", language="bash")
        st.markdown(ib("push 成功后 Railway 自动部署（2-5 分钟）"), unsafe_allow_html=True)
    st.divider()
    st.markdown("**🔑 Railway 环境变量（复制到 Dashboard）**")
    st.code("""LEDGER_ENABLED=0\nCLEARING_ENABLED=0\nSOCIAL_ENABLED=0\nHUB_JWT_SECRET=claw-prod-secret-2026\nHUB_MERCHANT_KEY=merchant-prod-key-2026\nWECHAT_APPID=wx1f7d608c84f6da6d\nHUB_RATE_LIMIT_PER_MIN=60""")

# ═══ TAB5 ════════════════════════════════
with tab5:
    st.subheader("⚙️ 配置管理")
    st.markdown("**mini_program_app/utils/config.js**")
    st.code("const BASE_URL = 'http://127.0.0.1:8765'; // 本地", language="javascript")
    st.code("const BASE_URL = 'https://project-claw-production.up.railway.app'; // 生产", language="javascript")
    st.divider()
    st.markdown("**🏗️ 系统架构**")
    st.markdown(ib("小程序 → Railway 信令塔 → Tailscale 暗网 → 本地 5090 集群 → LLM A2A 博弈"), unsafe_allow_html=True)
    st.code("""Railway (signaling_hub)
  ├─ /api/v1/auth/client          # 微信 OpenID 换 JWT
  ├─ /api/v1/trade/request        # 询价广播
  ├─ /api/v1/trade/request/stream # SSE 流式报价
  ├─ /api/v1/trade/execute        # 成交 + 分账
  ├─ /api/v1/merchants/online     # 商家心跳
  └─ /ws/merchant/{id}            # 商家 WS 长连接

Edge Box (5090×4, Tailscale)
  ├─ Qwen-2.5  A2A 博弈引擎
  ├─ VLM       视觉支付验证
  └─ RAG       商家菜单检索""")

st.markdown("""
<div style='text-align:center;margin-top:32px;color:#a0a0a0;font-size:12px'>
Project Claw v14.3 · 工业级控制台 · 1% 路由费 · A2A 博弈引擎 · 4×RTX5090 算力护城河
</div>
""", unsafe_allow_html=True)
