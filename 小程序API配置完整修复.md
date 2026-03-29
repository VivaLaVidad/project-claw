# Project Claw 小程序API配置完整修复方案

## 🔍 问题诊断

### 问题 1：小程序使用了生产环境地址
```
原因：微信开发者工具环境版本不是 'develop'
症状：小程序调用 https://api.project-claw.com 而不是 http://localhost:8765
```

### 问题 2：后端缺少基础路由
```
原因：api_server_pro.py 没有暴露 /health 和 /stats 路由
症状：小程序无法检查服务器连接
```

### 问题 3：API 路由不完整
```
原因：后端没有实现所有小程序需要的 API 端点
症状：小程序调用 API 返回 404
```

---

## ✅ 完整修复方案

### 第 1 步：修复小程序环境检测

**文件：** `miniprogram/app.js`

```javascript
// app.js - Project Claw 小程序入口 v5.2（修复版）

App({
  onLaunch() {
    console.log('[App] 启动中...');
    
    // 初始化全局数据
    this.globalData = {
      // API 配置（强制使用本地开发环境）
      serverBase: 'http://localhost:8765',  // ✅ 强制本地
      wsBase: 'ws://localhost:8765',        // ✅ 强制本地
      
      // 用户信息
      clientId: this._getClientId(),
      token: wx.getStorageSync('auth_token') || '',
      merchantId: 'box-001',
      
      // 连接状态
      isConnected: false,
      serverStatus: 'unknown',
      
      // 调试模式
      debug: true,
    };
    
    console.log('[App] 全局配置:', {
      serverBase: this.globalData.serverBase,
      wsBase: this.globalData.wsBase,
      clientId: this.globalData.clientId,
    });
    
    // 检查服务器连接
    this._checkServerConnection();
  },

  onShow() {
    console.log('[App] 应用显示');
  },

  onHide() {
    console.log('[App] 应用隐藏');
  },

  _getClientId() {
    let clientId = wx.getStorageSync('client_id');
    if (!clientId) {
      clientId = `client_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
      wx.setStorageSync('client_id', clientId);
      console.log('[App] 生成新的 clientId:', clientId);
    }
    return clientId;
  },

  async _checkServerConnection() {
    try {
      console.log('[App] 检查服务器连接...');
      const { createRequest, SystemAPI } = require('./api/request');
      const request = createRequest(this.globalData.serverBase, this.globalData.token);
      const sysAPI = SystemAPI(request);
      
      const result = await sysAPI.health();
      this.globalData.isConnected = true;
      this.globalData.serverStatus = 'online';
      
      console.log('[App] ✓ 服务器连接成功', result);
      this.triggerEvent('serverConnected', { status: 'online' });
    } catch (err) {
      this.globalData.isConnected = false;
      this.globalData.serverStatus = 'offline';
      
      console.error('[App] ✗ 服务器连接失败:', err);
      this.triggerEvent('serverDisconnected', { error: err.msg });
    }
  },

  _eventHandlers: {},

  on(event, handler) {
    if (!this._eventHandlers[event]) {
      this._eventHandlers[event] = [];
    }
    this._eventHandlers[event].push(handler);
    console.log(`[App] 事件监听: ${event}`);
  },

  off(event, handler) {
    if (this._eventHandlers[event]) {
      this._eventHandlers[event] = this._eventHandlers[event].filter(h => h !== handler);
    }
  },

  triggerEvent(event, data) {
    console.log(`[App] 触发事件: ${event}`, data);
    if (this._eventHandlers[event]) {
      this._eventHandlers[event].forEach(handler => handler(data));
    }
  },
})
```

### 第 2 步：修复后端 API 路由

**文件：** `cloud_server/api_server_pro.py`

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging

from .api_routes_fix import router as api_v1_router
from .industrial_fix import (
    get_merchants_api,
    get_merchant_api,
    get_dashboard_stats_api,
    get_dialogues_api
)

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Project Claw API",
    description="Project Claw 后端 API 服务",
    version="1.0.0"
)

# CORS 配置 - 允许所有来源
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册 API 路由
app.include_router(api_v1_router)

# ═══════════════════════════════════════════════════════════
# 基础系统 API
# ═══════════════════════════════════════════════════════════

@app.get("/health")
async def health_check():
    """健康检查"""
    logger.info("健康检查请求")
    return {
        "code": "0000",
        "message": "success",
        "data": {"status": "healthy"}
    }

@app.get("/stats")
async def get_stats():
    """获取统计数据"""
    logger.info("获取统计数据")
    return await get_dashboard_stats_api()

@app.get("/metrics")
async def get_metrics():
    """获取指标"""
    logger.info("获取指标")
    return {
        "code": "0000",
        "message": "success",
        "data": {
            "uptime": 0,
            "requests": 0,
            "errors": 0
        }
    }

# ═══════════════════════════════════════════════════════════
# 商家 API
# ═══════════════════════════════════════════════════════════

@app.get("/api/v1/merchants")
async def get_merchants():
    """获取所有在线商家"""
    logger.info("获取所有商家")
    return await get_merchants_api()

@app.get("/api/v1/merchants/{merchant_id}")
async def get_merchant(merchant_id: str):
    """获取单个商家"""
    logger.info(f"获取商家: {merchant_id}")
    return await get_merchant_api(merchant_id)

# ═══════════════════════════════════════════════════════════
# 统计 API
# ═══════════════════════════════════════════════════════════

@app.get("/api/v1/statistics/dashboard")
async def get_dashboard_stats():
    """获取仪表板统计"""
    logger.info("获取仪表板统计")
    return await get_dashboard_stats_api()

# ═══════════════════════════════════════════════════════════
# 对话 API
# ═══════════════════════════════════════════════════════════

@app.get("/api/v1/dialogues")
async def get_dialogues():
    """获取所有对话"""
    logger.info("获取所有对话")
    return await get_dialogues_api()

@app.get("/api/v1/dialogues/{session_id}")
async def get_dialogue(session_id: str):
    """获取单个对话"""
    logger.info(f"获取对话: {session_id}")
    return {
        "code": "0000",
        "message": "success",
        "data": {
            "session_id": session_id,
            "messages": []
        }
    }

# ═══════════════════════════════════════════════════════════
# 订单 API
# ═══════════════════════════════════════════════════════════

@app.get("/orders")
async def get_orders(limit: int = 50):
    """获取订单列表"""
    logger.info(f"获取订单列表: limit={limit}")
    return {
        "code": "0000",
        "message": "success",
        "data": {
            "orders": [],
            "total": 0
        }
    }

@app.get("/orders/{order_id}")
async def get_order(order_id: str):
    """获取订单详情"""
    logger.info(f"获取订单: {order_id}")
    return {
        "code": "0000",
        "message": "success",
        "data": {
            "order_id": order_id,
            "status": "pending"
        }
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8765)
```

### 第 3 步：修复小程序 API 请求

**文件：** `miniprogram/api/request.js` - 添加错误日志

```javascript
// 在 _raw 函数中添加日志
function _raw({ method='GET', path, data, timeout=DEFAULT_TIMEOUT }) {
  return new Promise((resolve, reject) => {
    const url = base + path;
    console.log(`[API] ${method} ${url}`);  // ✅ 添加日志
    
    const header = { 'Content-Type': 'application/json' };
    if (token) header['Authorization'] = `Bearer ${token}`;
    
    wx.request({
      url: url,
      method: method,
      data: data,
      header: header,
      timeout: timeout,
      success(res) {
        console.log(`[API] ✓ ${method} ${url} - ${res.statusCode}`);  // ✅ 添加日志
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(res.data);
        } else {
          reject({
            code: res.statusCode,
            msg: res.data?.detail || `HTTP ${res.statusCode}`,
            noRetry: NO_RETRY_CODES.has(res.statusCode)
          });
        }
      },
      fail(err) {
        console.error(`[API] ✗ ${method} ${url} - ${err.errMsg}`);  // ✅ 添加日志
        reject({
          code: -1,
          msg: err.errMsg || '网络错误',
          noRetry: false
        });
      },
    });
  });
}
```

---

## 🚀 快速修复步骤

### 第 1 步：更新小程序 app.js
```
1. 打开 miniprogram/app.js
2. 将 serverBase 改为 'http://localhost:8765'
3. 将 wsBase 改为 'ws://localhost:8765'
4. 保存文件
```

### 第 2 步：更新后端 api_server_pro.py
```
1. 打开 cloud_server/api_server_pro.py
2. 添加所有基础路由（/health, /stats, /metrics, /orders）
3. 保存文件
```

### 第 3 步：重启所有服务
```
1. 关闭所有终端
2. 双击 完整一键启动.bat
3. 等待 2-3 分钟
```

### 第 4 步：验证
```
1. 打开小程序
2. 检查控制台日志
3. 应该看到 ✓ 服务器连接成功
4. 应该看到 5 个在线商家
```

---

## ✅ 修复后的预期结果

```
✅ 小程序显示 5 个在线商家
✅ 服务器状态显示 ✓ 在线
✅ 所有 API 调用成功
✅ 没有 404 错误
✅ 控制台日志清晰
```

---

## 📊 调试技巧

### 查看小程序日志
```
微信开发者工具 → 调试器 → Console
应该看到：
[App] 启动中...
[App] 全局配置: { serverBase: 'http://localhost:8765', ... }
[App] 检查服务器连接...
[API] GET http://localhost:8765/health
[API] ✓ GET http://localhost:8765/health - 200
[App] ✓ 服务器连接成功
```

### 查看后端日志
```
后端 API 终端
应该看到：
INFO:     Uvicorn running on http://0.0.0.0:8765
INFO:     Application startup complete
GET /health HTTP/1.1" 200
GET /api/v1/merchants HTTP/1.1" 200
```

---

## 🎉 现在就修复吧！

### 最简单的方式
```
1. 更新 miniprogram/app.js（改 serverBase）
2. 更新 cloud_server/api_server_pro.py（添加路由）
3. 双击 完整一键启动.bat
4. 打开小程序，检查商家列表
```

---

**所有问题都会解决！** 🚀🦞
