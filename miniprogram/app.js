// app.js - Project Claw 小程序全局入口
const { createRequest } = require('./api/request');
const ProfileManager = require('./utils/profile');

App({
  globalData: {
    clientId: '',
    merchantId: '',
    userProfile: null,
    serverBase: 'http://127.0.0.1:8765',   // 生产时改为公网地址
    wsBase:     'ws://127.0.0.1:8765',
    token: '',                              // INTERNAL_API_TOKEN（如有）
    isConnected: false,
  },

  onLaunch() {
    this._initClientId();
    this._initProfile();
    console.log('[App] Project Claw 小程序启动');
  },

  onShow() {
    // 可在此做 token 刷新
  },

  // ─── 工具方法（全局可访问）───

  request(opts) {
    return createRequest(this.globalData.serverBase, this.globalData.token)(opts);
  },

  // ─── 私有初始化 ───

  _initClientId() {
    let id = wx.getStorageSync('client_id');
    if (!id) {
      id = 'c_' + Date.now() + '_' + Math.random().toString(36).slice(2, 8);
      wx.setStorageSync('client_id', id);
    }
    this.globalData.clientId = id;
    console.log('[App] clientId:', id);
  },

  _initProfile() {
    const saved = wx.getStorageSync('user_profile');
    if (saved) {
      this.globalData.userProfile = saved;
    } else {
      // 默认画像
      this.globalData.userProfile = ProfileManager.defaultClientProfile(this.globalData.clientId);
    }
  },
});
