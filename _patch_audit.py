import sys

path = 'd:/桌面/Project Claw/a2a_signaling_server.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

changes = 0

# 1. 加入导入
old1 = 'from cloud_server.dialogue_arena import DialogueArena'
new1 = 'from cloud_server.dialogue_arena import DialogueArena\nfrom audit_broadcaster import AuditBroadcaster'
if old1 in content:
    content = content.replace(old1, new1, 1)
    changes += 1
    print('OK: import added')
else:
    print('SKIP: import already present or not found')

# 2. 加入 audit 实例
old2 = 'manager = ConnectionManager()'
new2 = 'audit = AuditBroadcaster()\nmanager = ConnectionManager()'
if 'audit = AuditBroadcaster()' not in content:
    content = content.replace(old2, new2, 1)
    changes += 1
    print('OK: audit instance added')
else:
    print('SKIP: audit already instantiated')

# 3. startup 中初始化锁
old3 = 'asyncio.ensure_future(manager.heartbeat_loop())'
new3 = 'audit.init_lock()\n    asyncio.ensure_future(manager.heartbeat_loop())'
if 'audit.init_lock()' not in content:
    content = content.replace(old3, new3, 1)
    changes += 1
    print('OK: audit.init_lock() added to startup')
else:
    print('SKIP: init_lock already present')

# 4. 在 /intent 路由中插入 audit emit
old4 = 'result = await manager.broadcast_intent(intent)\n    manager.idempotency.set(key, result.model_dump())\n    return result'
new4 = '''result = await manager.broadcast_intent(intent)
    # 审计广播
    import asyncio as _aio
    _aio.ensure_future(audit.emit({"type":"intent","role":"info","text":f"[{result.intent_id}] C端广播: {intent.demand_text} max=¥{intent.max_price} merchants={result.total_merchants}"}))
    if result.offers:
        for _o in result.offers[:3]:
            _aio.ensure_future(audit.emit({"type":"agent","role":"seller","text":f"[B端Agent:{_o.merchant_id}] 报价 ¥{_o.final_price} score={_o.match_score:.1f}"}))
        best = result.offers[0]
        _aio.ensure_future(audit.emit({"type":"deal","role":"deal","text":f"[成交] {best.merchant_id} ¥{best.final_price} 节省¥{round(intent.max_price-best.final_price,2)}"}))
        audit.record_trade(best.merchant_id, intent.demand_text, intent.max_price, best.final_price, best.offer_tags)
    manager.idempotency.set(key, result.model_dump())
    return result'''
if 'audit.emit' not in content:
    if old4 in content:
        content = content.replace(old4, new4, 1)
        changes += 1
        print('OK: audit emit in /intent')
    else:
        print('WARN: /intent result block not found exactly, skip')

# 5. 加 /ws/audit_stream 端点
audit_ws_endpoint = '''

@app.websocket("/ws/audit_stream")
async def audit_stream_ws(websocket: WebSocket):
    """\u4e0a帝视角监控大屏实时审计流"""
    await websocket.accept()
    q = await audit.subscribe()
    # 先发送当前快照
    snap = audit.snapshot(online_merchants=len(manager._merchants))
    await websocket.send_text(json.dumps({"type": "snapshot", **snap}, ensure_ascii=False))
    try:
        while True:
            try:
                event = await asyncio.wait_for(q.get(), timeout=20.0)
                await websocket.send_text(json.dumps(event, ensure_ascii=False))
            except asyncio.TimeoutError:
                # 心跳
                await websocket.send_text(json.dumps({"type": "ping", "ts": time.time()}))
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning(f"[audit_stream] error: {e}")
    finally:
        await audit.unsubscribe(q)


@app.get("/audit/snapshot")
async def audit_snapshot_http():
    """HTTP 拉取当前审计快照（Streamlit 初始化用）"""
    snap = audit.snapshot(online_merchants=len(manager._merchants))
    stats = manager.stats()
    return {**snap, **stats}
'''
if '/ws/audit_stream' not in content:
    # 插在文件末尾
    content = content.rstrip() + '\n' + audit_ws_endpoint
    changes += 1
    print('OK: /ws/audit_stream endpoint added')
else:
    print('SKIP: audit_stream already exists')

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

print(f'Done. {changes} changes applied.')
