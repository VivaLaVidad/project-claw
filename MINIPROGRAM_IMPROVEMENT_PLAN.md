# 小程序配置改善方案 v1.0

## 🔍 发现的问题

### 问题 1：API 基础 URL 未正确配置
```javascript
// 当前状态：request.js 中没有设置默认的 API_BASE_URL
// 导致：小程序无法连接到后端服务
```

### 问题 2：app.js 中缺少全局配置
```javascript
// 当前状态：app.js 没有初始化 globalData.serverBase
// 导致：所有 API 请求都失败
```

### 问题 3：网络超时配置过短
```javascript
// 当前状态：request 超时 15000ms，但后端可能需要更长时间
// 导致：请求经常超时
```

### 问题 4：缺少错误日志和调试信息
```javascript
// 当前状态：错误信息不清晰
// 导致：难以定位问题
```

---

## ✅ 改善方案

### 改善 1：创建改进的 app.js

创建文件：`miniprogram/app.js`

```javascript
// app.js - Project Claw 小程序入口 v5.1（改进版）

App({
  onLaunch() {
    console.log('[App] 启动中...');
    
    // 初始化全局数据
    this.globalData = {
      // API 配置（根据环境自动切换）
      serverBase: this._getServerBase(),
      wsBase: this._getWSBase(),
      
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

  // ── 配置方法 ──────────────────────────────────────────
  _getServerBase() {
    // 开发环境：本地 localhost
    // 生产环境：实际服务器地址
    const isDev = wx.getAccountInfoSync().miniProgram.envVersion === 'develop';
    
    if (isDev) {
      // 本地开发：使用 localhost
      return 'http://localhost:8765';
    } else {
      // 生产环境：使用实际服务器
      return 'https://api.project-claw.com';
    }
  },

  _getWSBase() {
    const isDev = wx.getAccountInfoSync().miniProgram.envVersion === 'develop';
    
    if (isDev) {
      return 'ws://localhost:8765';
    } else {
      return 'wss://api.project-claw.com';
    }
  },

  _getClientId() {
    let clientId = wx.getStorageSync('client_id');
    if (!clientId) {
      clientId = `client_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
      wx.setStorageSync('client_id', clientId);
    }
    return clientId;
  },

  async _checkServerConnection() {
    try {
      const { createRequest, SystemAPI } = require('./api/request');
      const request = createRequest(this.globalData.serverBase, this.globalData.token);
      const sysAPI = SystemAPI(request);
      
      const result = await sysAPI.health();
      this.globalData.isConnected = true;
      this.globalData.serverStatus = 'online';
      
      console.log('[App] ✓ 服务器连接成功', result);
      
      // 触发全局事件
      this.triggerEvent('serverConnected', { status: 'online' });
    } catch (err) {
      this.globalData.isConnected = false;
      this.globalData.serverStatus = 'offline';
      
      console.error('[App] ✗ 服务器连接失败:', err);
      
      // 触发全局事件
      this.triggerEvent('serverDisconnected', { error: err.msg });
    }
  },

  // ── 全局事件系统 ──────────────────────────────────────
  _eventHandlers: {},

  on(event, handler) {
    if (!this._eventHandlers[event]) {
      this._eventHandlers[event] = [];
    }
    this._eventHandlers[event].push(handler);
  },

  off(event, handler) {
    if (this._eventHandlers[event]) {
      this._eventHandlers[event] = this._eventHandlers[event].filter(h => h !== handler);
    }
  },

  triggerEvent(event, data) {
    if (this._eventHandlers[event]) {
      this._eventHandlers[event].forEach(handler => handler(data));
    }
  },
});
```

### 改善 2：改进的 request.js

在 `miniprogram/api/request.js` 中添加日志和错误处理：

```javascript
// 在 createRequest 函数中添加日志

function createRequest(baseUrl, token) {
  const base = (baseUrl || '').replace(/\/$/,'');
  
  console.log('[Request] 初始化，基础 URL:', base);

  function _sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

  function _raw({ method='GET', path, data, timeout=DEFAULT_TIMEOUT }) {
    const fullUrl = base + path;
    console.log(`[Request] ${method} ${fullUrl}`, data ? `(data: ${JSON.stringify(data).substring(0, 100)})` : '');
    
    return new Promise((resolve, reject) => {
      const header = { 'Content-Type': 'application/json' };
      if (token) header['Authorization'] = `Bearer ${token}`;
      
      wx.request({
        url: fullUrl,
        method,
        data,
        header,
        timeout,
        success(res) {
          console.log(`[Request] ✓ ${method} ${path} - ${res.statusCode}`, res.data);
          
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
          console.error(`[Request] ✗ ${method} ${path} - 网络错误`, err);
          reject({
            code: -1,
            msg: err.errMsg || '网络错误',
            noRetry: false
          });
        },
      });
    });
  }

  async function request(opts) {
    let lastErr;
    for (let i = 0; i < MAX_RETRIES; i++) {
      try {
        return await _raw(opts);
      } catch (err) {
        lastErr = err;
        console.warn(`[Request] 重试 ${i + 1}/${MAX_RETRIES}:`, err.msg);
        
        if (err.noRetry) throw err;
        if (i < MAX_RETRIES - 1) {
          const delay = RETRY_BASE_MS * Math.pow(2, i) + Math.random() * 100;
          await _sleep(delay);
        }
      }
    }
    throw lastErr;
  }
  
  return request;
}
```

### 改善 3：改进的 index.js

在 `miniprogram/pages/index/index.js` 中添加调试信息：

```javascript
// 在 onLoad 中添加调试日志

onLoad() {
  const app = getApp();
  
  console.log('[Index] 页面加载');
  console.log('[Index] 全局配置:', {
    serverBase: app.globalData.serverBase,
    clientId: app.globalData.clientId,
    isConnected: app.globalData.isConnected,
  });
  
  this._request = createRequest(app.globalData.serverBase, app.globalData.token);
  const profile = ProfileManager.loadClientProfile(app.globalData.clientId);
  const history = ProfileManager.getSearchHistory();
  
  this.setData({ profile, searchHistory: history });
  
  // 监听服务器连接状态
  app.on('serverConnected', () => {
    console.log('[Index] 服务器已连接');
    this.setData({ serverStatus: 'online' });
    this._checkServerStatus();
  });
  
  app.on('serverDisconnected', (data) => {
    console.log('[Index] 服务器已断开:', data);
    this.setData({ serverStatus: 'offline' });
  });
  
  this._checkServerStatus();
},

async _checkServerStatus() {
  try {
    console.log('[Index] 检查服务器状态...');
    const { SystemAPI } = require('../../api/request');
    const sysAPI = SystemAPI(this._request);
    const result = await sysAPI.health();
    
    console.log('[Index] ✓ 服务器在线:', result);
    this.setData({ serverStatus: 'online' });
    getApp().globalData.isConnected = true;
  } catch (e) {
    console.error('[Index] ✗ 服务器离线:', e);
    this.setData({ serverStatus: 'offline' });
    getApp().globalData.isConnected = false;
  }
},
```

### 改善 4：改进的 app.json

```json
{
  "pages": [
    "pages/index/index",
    "pages/dialogue/dialogue",
    "pages/orders/orders",
    "pages/merchant/merchant"
  ],
  "window": {
    "backgroundTextStyle": "light",
    "navigationBarBackgroundColor": "#1a1a2e",
    "navigationBarTitleText": "Project Claw",
    "navigationBarTextStyle": "white",
    "backgroundColor": "#f5f5f7",
    "enablePullDownRefresh": true
  },
  "tabBar": {
    "color": "#888888",
    "selectedColor": "#e94560",
    "backgroundColor": "#1a1a2e",
    "borderStyle": "black",
    "list": [
      {
        "pagePath": "pages/index/index",
        "text": "发现",
        "iconPath": "icons/discover.png",
        "selectedIconPath": "icons/discover-active.png"
      },
      {
        "pagePath": "pages/orders/orders",
        "text": "订单",
        "iconPath": "icons/orders.png",
        "selectedIconPath": "icons/orders-active.png"
      },
      {
        "pagePath": "pages/merchant/merchant",
        "text": "商家",
        "iconPath": "icons/merchant.png",
        "selectedIconPath": "icons/merchant-active.png"
      }
    ]
  },
  "networkTimeout": {
    "request": 20000,
    "connectSocket": 15000,
    "uploadFile": 30000,
    "downloadFile": 30000
  },
  "permission": {
    "scope.userLocation": {
      "desc": "用于匹配附近商家"
    }
  },
  "requiredBackgroundModes": [
    "audio",
    "location"
  ],
  "sitemapLocation": "sitemap.json",
  "lazyCodeLoading": "requiredComponents",
  "debug": true
}
```

---

## 🚀 改善后的启动流程

### 第 1 步：启动后端服务
```powershell
cd "d:\桌面\Project Claw"
venv\Scripts\activate.bat
python -m uvicorn cloud_server.api_server_pro:app --host 0.0.0.0 --port 8765 --reload
```

### 第 2 步：在微信开发者工具中
```
1. 打开项目：d:\桌面\Project Claw\miniprogram
2. 点击"编译"
3. 打开"控制台"查看日志
4. 应该看到：
   [App] ✓ 服务器连接成功
   [Index] ✓ 服务器在线
```

### 第 3 步：查看日志
```
控制台应该显示：
[App] 启动中...
[App] 全局配置: { serverBase: 'http://localhost:8765', ... }
[Request] 初始化，基础 URL: http://localhost:8765
[Index] 页面加载
[Index] 检查服务器状态...
[Request] GET /health
[Index] ✓ 服务器在线
```

---

## 📊 改善效果

```
改善前：
❌ 在线商家显示 0
❌ 无法连接到后端
❌ 错误信息不清晰

改善后：
✅ 在线商家显示正确数量
✅ 自动连接到后端
✅ 详细的调试日志
✅ 自动重试机制
✅ 错误处理完善
```

---

## 📝 总结

这些改善包括：
1. ✅ 正确的 API 基础 URL 配置
2. ✅ 全局数据初始化
3. ✅ 详细的日志记录
4. ✅ 自动服务器连接检查
5. ✅ 更长的网络超时时间
6. ✅ 全局事件系统
7. ✅ 调试模式支持

---

**现在就应用这些改善吧！** 🚀
