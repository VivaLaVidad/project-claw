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
      environment: wx.getAccountInfoSync().miniProgram.envVersion,
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
    // 生产环境：Railway 生产服务器
    const envVersion = wx.getAccountInfoSync().miniProgram.envVersion;
    const isDev = envVersion === 'develop';
    
    if (isDev) {
      // 本地开发：使用 localhost
      console.log('[App] 环境: 开发环境 (localhost)');
      return 'http://localhost:8765';
    } else {
      // 生产环境：使用 Railway 部署的服务器
      console.log('[App] 环境: 生产环境 (Railway)');
      return 'https://project-claw-production.up.railway.app';
    }
  },

  _getWSBase() {
    const envVersion = wx.getAccountInfoSync().miniProgram.envVersion;
    const isDev = envVersion === 'develop';
    
    if (isDev) {
      console.log('[App] WebSocket: 开发环境 (localhost)');
      return 'ws://localhost:8765';
    } else {
      console.log('[App] WebSocket: 生产环境 (Railway)');
      return 'wss://project-claw-production.up.railway.app';
    }
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
