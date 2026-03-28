"""
Project Claw - 上帝视角监控大屏 v2.0
真实数据驱动：Railway Hub /audit/snapshot + /ws/audit_stream
演示降级：后端离线时自动切 Mock 数据流
"""
import streamlit as st
import pandas as pd
import pydeck as pdk
import json, time, threading, queue, requests, random
from datetime import datetime
from collections import deque
try:
    import websocket
    HAS_WS = True
except ImportError:
    HAS_WS = False

BACKEND_HTTP = "https://project-claw-production.up.railway.app"
BACKEND_WS   = "wss://project-claw-production.up.railway.app"

st.set_page_config(page_title="Project Claw · 上帝视角", page_icon="🦞", layout="wide", initial_sidebar_state="collapsed")
st.markdown("""<style>
[data-testid="stAppViewContainer"]{background:#0d0d0f}
[data-testid="stHeader"]{background:transparent}
.block-container{padding-top:1rem}
.mbox{background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.08);border-radius:16px;padding:24px;text-align:center}
.mlabel{font-size:13px;color:rgba(255,255,255,.5);margin-bottom:8px}
.mvg{font-size:56px;font-weight:800;color:#30d158;line-height:1}
.mvb{font-size:56px;font-weight:800;color:#5ac8fa;line-height:1}
.mvr{font-size:56px;font-weight:800;color:#ff3b5c;line-height:1}
.logbox{background:#1a1a2e;border-radius:12px;padding:16px;font-family:'Monaco','Courier New',monospace;font-size:12px;height:460px;overflow-y:auto}
.li{color:#636366}.la{color:#5ac8fa}.ls{color:#ff9f0a}.ld{color:#30d158;font-weight:bold}.lw{color:#ff3b5c}
</style>""", unsafe_allow_html=True)

# ── Session state ──
for k,v in [("logs",deque(maxlen=300)),("online_merchants",0),("total_negotiations",0),
            ("total_savings",0.0),("recent_trades",[]),("ws_status","connecting"),
            ("evq",None),("ws_started",False),("mock_mode",False)]:
    if k not in st.session_state: st.session_state[k]=v
if st.session_state.evq is None:
    st.session_state.evq = queue.Queue(maxsize=500)

MERCHANTS = [
    {"id":"box-001","name":"王记快餐", "lat":31.1304,"lon":121.4298,"r":255,"g":107,"b":53},
    {"id":"box-002","name":"小杨生煎", "lat":31.1310,"lon":121.4305,"r":255,"g":59, "b":92},
    {"id":"box-003","name":"鲜得来",   "lat":31.1295,"lon":121.4290,"r":48, "g":209,"b":88},
    {"id":"box-004","name":"大壶春",   "lat":31.1320,"lon":121.4310,"r":10, "g":132,"b":255},
    {"id":"box-005","name":"南翔馄饨", "lat":31.1300,"lon":121.4315,"r":255,"g":159,"b":10},
    {"id":"box-006","name":"蟹壳黄",   "lat":31.1308,"lon":121.4285,"r":175,"g":82, "b":222},
    {"id":"box-007","name":"绿波廊",   "lat":31.1312,"lon":121.4300,"r":0,  "g":199,"b":190},
    {"id":"box-008","name":"龙华素斋", "lat":31.1305,"lon":121.4308,"r":255,"g":204,"b":0},
]
MOCK_ITEMS=["牛肉面","生煎包","馄饨","小笼包","蟹壳黄","素面","炸春卷"]

def fetch_snapshot():
    try:
        r=requests.get(f"{BACKEND_HTTP}/audit/snapshot",timeout=4)
        if r.status_code==200: return r.json()
    except: pass
    return None

def ws_thread(evq):
    if not HAS_WS:
        evq.put_nowait({"_error":"websocket-client not installed"}); return
    def on_msg(app,msg):
        try: evq.put_nowait({"_raw":msg})
        except: pass
    def on_err(app,e): evq.put_nowait({"_error":str(e)})
    def on_close(app,*a): evq.put_nowait({"_closed":True})
    def on_open(app): evq.put_nowait({"_connected":True})
    app=websocket.WebSocketApp(f"{BACKEND_WS}/ws/audit_stream",
        on_open=on_open,on_message=on_msg,on_error=on_err,on_close=on_close)
    app.run_forever(ping_interval=20,ping_timeout=10,reconnect=5)

if not st.session_state.ws_started:
    threading.Thread(target=ws_thread,args=(st.session_state.evq,),daemon=True).start()
    st.session_state.ws_started=True

def process_events():
    eq=st.session_state.evq; n=0
    while not eq.empty() and n<60:
        try: item=eq.get_nowait()
        except: break
        n+=1
        if "_connected" in item:
            st.session_state.ws_status="online"; st.session_state.mock_mode=False
            snap=fetch_snapshot()
            if snap:
                st.session_state.online_merchants=snap.get("online_merchants",0)
                st.session_state.total_negotiations=snap.get("total_negotiations",0)
                st.session_state.total_savings=snap.get("total_savings",0.0)
                st.session_state.recent_trades=snap.get("recent_trades",[])
        elif "_error" in item or "_closed" in item:
            st.session_state.ws_status="offline"; st.session_state.mock_mode=True
        elif "_raw" in item:
            try: evt=json.loads(item["_raw"])
            except: continue
            if evt.get("type")=="snapshot":
                st.session_state.online_merchants=evt.get("online_merchants",0)
                st.session_state.total_negotiations=evt.get("total_negotiations",0)
                st.session_state.total_savings=evt.get("total_savings",0.0)
                st.session_state.recent_trades=evt.get("recent_trades",[])
            elif evt.get("type")!="ping":
                ts=datetime.fromtimestamp(evt.get("ts",time.time())).strftime("%H:%M:%S")
                st.session_state.logs.append({"ts":ts,"type":evt.get("type","info"),"text":evt.get("text",str(evt))})
                if evt.get("type")=="deal":
                    st.session_state.total_negotiations+=1
                    st.session_state.total_savings+=evt.get("savings",0)
                    st.session_state.recent_trades.append(evt)

def run_mock_tick():
    """演示模式：每次 rerun 注入1条 mock 事件"""
    if not st.session_state.mock_mode: return
    m=random.choice(MERCHANTS); item=random.choice(MOCK_ITEMS)
    n=round(random.uniform(12,28),2); f=round(n*random.uniform(0.85,0.97),2)
    s=round(n-f,2)
    ts=datetime.now().strftime("%H:%M:%S")
    evts=[
        {"ts":ts,"type":"info","text":f"📡 C端广播: {item} max=¥{n}"},
        {"ts":ts,"type":"agent","text":f"🤖 [B端:{m['name']}] 报价¥{n}"},
        {"ts":ts,"type":"agent","text":f"🧠 [C端Agent] 目标¥{f}，砍价中..."},
        {"ts":ts,"type":"deal","text":f"✅ 成交! {m['name']} {item} ¥{f} 节省¥{s}"},
    ]
    for e in evts: st.session_state.logs.append(e)
    st.session_state.total_negotiations+=1
    st.session_state.total_savings+=s
    st.session_state.online_merchants=random.randint(5,8)
    st.session_state.recent_trades.append({"merchant_id":m["id"],"item":item,
        "normal_price":n,"final_price":f,"savings":s,"ts":time.time()})

process_events()

run_mock_tick()

st.markdown("""
<div style='text-align:center;padding:16px 0 8px'>
  <h1 style='font-size:44px;font-weight:800;color:#f5f5f7;margin:0'>🦞 Project Claw</h1>
  <p style='font-size:16px;color:rgba(255,255,255,.45);margin:6px 0 0'>A2A 智能买手 · 上帝视角监控大屏</p>
</div>
""", unsafe_allow_html=True)

ws_col, demo_col = st.columns([3,1])
with ws_col:
    if st.session_state.ws_status=="online":
        st.markdown("<span style='color:#30d158;font-size:13px'>● Railway 后端已连接（实时数据）</span>",unsafe_allow_html=True)
    elif st.session_state.ws_status=="connecting":
        st.markdown("<span style='color:#ff9f0a;font-size:13px'>◌ 正在连接 Railway 后端...</span>",unsafe_allow_html=True)
    else:
        st.markdown("<span style='color:#ff3b5c;font-size:13px'>● 后端离线 — 演示模式</span>",unsafe_allow_html=True)
with demo_col:
    if st.button("🎭 注入演示数据",width='stretch'):
        st.session_state.mock_mode=True
        run_mock_tick()

st.markdown("### 📊 去中心化数据罗盘")
c1,c2,c3=st.columns(3)
with c1:
    st.markdown(f"<div class='mbox'><div class='mlabel'>🟢 活跃龙虾节点</div><div class='mvg'>{st.session_state.online_merchants}</div></div>",unsafe_allow_html=True)
with c2:
    st.markdown(f"<div class='mbox'><div class='mlabel'>⚡ 今日砍价次数</div><div class='mvb'>{st.session_state.total_negotiations}</div></div>",unsafe_allow_html=True)
with c3:
    st.markdown(f"<div class='mbox'><div class='mlabel'>💰 累计节省金额</div><div class='mvr'>¥{st.session_state.total_savings:.0f}</div></div>",unsafe_allow_html=True)

# ── 资金清算面板（接入 EscrowManager）──────────────────────────
try:
    from cloud_server.clearing_service import escrow_manager
    _summary = escrow_manager.summary()
    st.markdown("### 💳 资金清算账户（实时）")
    f1,f2,f3,f4 = st.columns(4)
    def _fin_box(label, val, color="#30d158"):
        return f"<div class='mbox'><div class='mlabel'>{label}</div><div style='font-size:36px;font-weight:800;color:{color};line-height:1'>¥{val:.2f}</div></div>"
    with f1: st.markdown(_fin_box("💰 已结算总额",     _summary["total_settled_yuan"]),  unsafe_allow_html=True)
    with f2: st.markdown(_fin_box("🏪 商家到账(99%)",  _summary["merchant_revenue_yuan"]), unsafe_allow_html=True)
    with f3: st.markdown(_fin_box("🏦 平台抽佣(1%)",   _summary["platform_revenue_yuan"], "#ff9f0a"), unsafe_allow_html=True)
    with f4: st.markdown(_fin_box("🔒 冻结中",         _summary["total_frozen_yuan"],    "#5ac8fa"), unsafe_allow_html=True)
    st.caption(f"📋 托管统计 — 结算:{_summary['settled_count']} | 冻结:{_summary['frozen_count']} | 退款:{_summary['refunded_count']} | 失败:{_summary['failed_count']}")
except Exception:
    pass

map_col,log_col=st.columns([1,1])
with map_col:
    st.markdown("### 🗺️ 实时交易地图")
    map_df=pd.DataFrame([{"lat":m["lat"],"lon":m["lon"],"name":m["name"],"color":[m["r"],m["g"],m["b"],200]} for m in MERCHANTS])
    lines=[]
    for t in st.session_state.recent_trades[-5:]:
        mid=t.get("merchant_id","")
        merch=next((m for m in MERCHANTS if m["id"]==mid),None)
        if merch:
            lines.append({"src":[121.4300,31.1305],"tgt":[merch["lon"],merch["lat"]],"color":[48,209,88,180]})
    layers=[pdk.Layer("ScatterplotLayer",data=map_df,get_position=["lon","lat"],get_color="color",get_radius=80,pickable=True)]
    if lines:
        layers.append(pdk.Layer("LineLayer",data=pd.DataFrame(lines),get_source_position="src",get_target_position="tgt",get_color="color",get_width=3))
    st.pydeck_chart(pdk.Deck(layers=layers,initial_view_state=pdk.ViewState(latitude=31.1305,longitude=121.4300,zoom=15,pitch=0),map_style="mapbox://styles/mapbox/dark-v11"),width='stretch')

with log_col:
    st.markdown("### 🧠 A2A 脑机接口 · 实时 CoT 日志")
    log_css={"info":"li","agent":"la","seller":"ls","deal":"ld","warn":"lw"}
    rows=[]
    for entry in list(st.session_state.logs)[-60:]:
        cls=log_css.get(entry.get("type","info"),"li")
        rows.append(f"<span class='{cls}'>[{entry['ts']}] {entry['text']}</span>")
    if not rows: rows=["<span class='li'>等待 A2A 谈判数据流...</span>"]
    st.markdown("<div class='logbox'>"+("<br>".join(rows))+"</div>",unsafe_allow_html=True)

if st.session_state.recent_trades:
    st.markdown("### 📈 今日成交明细")
    import pandas as _pd2
    df=_pd2.DataFrame(st.session_state.recent_trades[-50:])
    if "ts" in df.columns:
        from datetime import datetime as _dt
        df["时间"]=df["ts"].apply(lambda x:_dt.fromtimestamp(float(x)).strftime("%H:%M:%S"))
    cols=[c for c in ["时间","merchant_id","item","normal_price","final_price","savings"] if c in df.columns]
    rename={"merchant_id":"商家","item":"商品","normal_price":"原价","final_price":"成交价","savings":"节省"}
    st.dataframe(df[cols].rename(columns=rename).tail(20),width='stretch',hide_index=True)

time.sleep(2)
st.rerun()
