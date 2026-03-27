"""修复 Railway WS 403：去掉 a2a merchant/dialogue WS 端点的 token 校验"""
path = 'd:/桌面/Project Claw/a2a_signaling_server.py'
with open(path, 'r', encoding='utf-8') as f:
    c = f.read()

# WS 端点不能用 HTTP Depends 做 token 校验（WS 握手时 Header 不一样）
# 改为在 query param 里传 token，或者直接对内网/可信源开放
# 最简单方案：在 ws 端点里手动校验 query param token

old1 = '@app.websocket("/ws/a2a/merchant/{merchant_id}")\nasync def a2a_merchant_ws(websocket: WebSocket, merchant_id: str, distance_km: float = 0.0):'
new1 = '@app.websocket("/ws/a2a/merchant/{merchant_id}")\nasync def a2a_merchant_ws(websocket: WebSocket, merchant_id: str, distance_km: float = 0.0, token: str = ""):'
if old1 in c:
    c = c.replace(old1, new1, 1)
    print('OK: merchant ws token param added')
else:
    print('SKIP: merchant ws not found')

old2 = '@app.websocket("/ws/a2a/dialogue/merchant/{merchant_id}")\nasync def a2a_dialogue_merchant_ws(websocket: WebSocket, merchant_id: str):'
new2 = '@app.websocket("/ws/a2a/dialogue/merchant/{merchant_id}")\nasync def a2a_dialogue_merchant_ws(websocket: WebSocket, merchant_id: str, token: str = ""):'
if old2 in c:
    c = c.replace(old2, new2, 1)
    print('OK: dialogue merchant ws token param added')
else:
    print('SKIP: dialogue merchant ws not found')

# 在 register_merchant 之前插入 token 校验（允许空 token 也通过，兼容未配置情况）
old3 = '    await trade_arena.register_merchant(merchant_id=merchant_id, ws=websocket, distance_km=distance_km)'
new3 = '''    # Token 校验（INTERNAL_API_TOKEN 未配置时开放）
    _expected = settings.INTERNAL_API_TOKEN
    if _expected and token != _expected:
        await websocket.accept()
        await websocket.send_text(json.dumps({"type":"error","error":"unauthorized"}))
        await websocket.close(code=4001)
        return
    await trade_arena.register_merchant(merchant_id=merchant_id, ws=websocket, distance_km=distance_km)'''
if old3 in c:
    c = c.replace(old3, new3, 1)
    print('OK: merchant ws auth guard added')
else:
    print('SKIP: register_merchant line not found')

with open(path, 'w', encoding='utf-8') as f:
    f.write(c)
print('Done.')
