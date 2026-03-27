path = 'd:/桌面/Project Claw/god_mode_dashboard.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

ui_code = '''
run_mock_tick()

st.markdown("""
<div style='text-align:center;padding:16px 0 8px'>
  <h1 style='font-size:44px;font-weight:800;color:#f5f5f7;margin:0'>\U0001f99e Project Claw</h1>
  <p style='font-size:16px;color:rgba(255,255,255,.45);margin:6px 0 0'>A2A \u667a\u80fd\u4e70\u624b \u00b7 \u4e0a\u5e1d\u89c6\u89d2\u76d1\u63a7\u5927\u5c4f</p>
</div>
""", unsafe_allow_html=True)

ws_col, demo_col = st.columns([3,1])
with ws_col:
    if st.session_state.ws_status=="online":
        st.markdown("<span style='color:#30d158;font-size:13px'>\u25cf Railway \u540e\u7aef\u5df2\u8fde\u63a5\uff08\u5b9e\u65f6\u6570\u636e\uff09</span>",unsafe_allow_html=True)
    elif st.session_state.ws_status=="connecting":
        st.markdown("<span style='color:#ff9f0a;font-size:13px'>\u25cc \u6b63\u5728\u8fde\u63a5 Railway \u540e\u7aef...</span>",unsafe_allow_html=True)
    else:
        st.markdown("<span style='color:#ff3b5c;font-size:13px'>\u25cf \u540e\u7aef\u79bb\u7ebf \u2014 \u6f14\u793a\u6a21\u5f0f</span>",unsafe_allow_html=True)
with demo_col:
    if st.button("\U0001f3ad \u6ce8\u5165\u6f14\u793a\u6570\u636e",use_container_width=True):
        st.session_state.mock_mode=True
        run_mock_tick()

st.markdown("### \U0001f4ca \u53bb\u4e2d\u5fc3\u5316\u6570\u636e\u7f57\u76d8")
c1,c2,c3=st.columns(3)
with c1:
    st.markdown(f"<div class=\'mbox\'><div class=\'mlabel\'>\U0001f7e2 \u6d3b\u8dc3\u9f99\u867e\u8282\u70b9</div><div class=\'mvg\'>{st.session_state.online_merchants}</div><div style=\'font-size:12px;color:rgba(255,255,255,.3);margin-top:8px\'></div></div>",unsafe_allow_html=True)
with c2:
    st.markdown(f"<div class=\'mbox\'><div class=\'mlabel\'>\u26a1 \u4eca\u65e5\u780d\u4ef7\u6b21\u6570</div><div class=\'mvb\'>{st.session_state.total_negotiations}</div><div style=\'font-size:12px;color:rgba(255,255,255,.3);margin-top:8px\'></div></div>",unsafe_allow_html=True)
with c3:
    st.markdown(f"<div class=\'mbox\'><div class=\'mlabel\'>\U0001f4b0 \u7d2f\u8ba1\u4e3a\u5546\u5bb6\u593a\u56de</div><div class=\'mvr\'>\xa5{st.session_state.total_savings:.0f}</div><div style=\'font-size:12px;color:rgba(255,255,255,.3);margin-top:8px\'></div></div>",unsafe_allow_html=True)

map_col,log_col=st.columns([1,1])
with map_col:
    st.markdown("### \U0001f5fa\ufe0f \u5b9e\u65f6\u4ea4\u6613\u5730\u56fe")
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
    st.pydeck_chart(pdk.Deck(layers=layers,initial_view_state=pdk.ViewState(latitude=31.1305,longitude=121.4300,zoom=15,pitch=0),map_style="mapbox://styles/mapbox/dark-v11"),use_container_width=True)

with log_col:
    st.markdown("### \U0001f9e0 A2A \u8111\u673a\u63a5\u53e3 \u00b7 \u5b9e\u65f6 CoT \u65e5\u5fd7")
    log_css={"info":"li","agent":"la","seller":"ls","deal":"ld","warn":"lw"}
    rows=[]
    for entry in list(st.session_state.logs)[-60:]:
        cls=log_css.get(entry.get("type","info"),"li")
        rows.append(f"<span class=\'{cls}\'>[{entry[\'ts\']}] {entry[\'text\']}</span>")
    if not rows: rows=["<span class=\'li\'>\u7b49\u5f85 A2A \u8c08\u5224\u6570\u636e\u6d41...</span>"]
    st.markdown("<div class=\'logbox\'>"+("<br>".join(rows))+"</div>",unsafe_allow_html=True)

if st.session_state.recent_trades:
    st.markdown("### \U0001f4c8 \u4eca\u65e5\u6210\u4ea4\u660e\u7ec6")
    import pandas as _pd2
    df=_pd2.DataFrame(st.session_state.recent_trades[-50:])
    if "ts" in df.columns:
        from datetime import datetime as _dt
        df["\u65f6\u95f4"]=df["ts"].apply(lambda x:_dt.fromtimestamp(float(x)).strftime("%H:%M:%S"))
    cols=[c for c in ["\u65f6\u95f4","merchant_id","item","normal_price","final_price","savings"] if c in df.columns]
    rename={"merchant_id":"\u5546\u5bb6","item":"\u5546\u54c1","normal_price":"\u539f\u4ef7","final_price":"\u6210\u4ea4\u4ef7","savings":"\u8282\u7701"}
    st.dataframe(df[cols].rename(columns=rename).tail(20),use_container_width=True,hide_index=True)

time.sleep(2)
st.rerun()
'''

if 'st.rerun()' not in content:
    with open(path, 'a', encoding='utf-8') as f:
        f.write(ui_code)
    print('OK: UI appended')
else:
    print('SKIP: UI already present')
