// app.js - Project Claw 小程序全局入口 v2.0
const { createRequest, SystemAPI } = require('./api/request');
const ProfileManager = require('./utils/profile');

App({
  globalData: {
    clientId: '',
    merchantId: 'box-001',
    userProfile: null,
    serverBase: 'https://project-claw-production.up.railway.app',
    wsBase:     'wss://project-claw-production.up.railway.app',
    token: '',
    isConnected: false,
    serverVersion: '',
    onlineMerchants: 0,
  },

  onLaunch() {
    this._initClientId();
    this._initProfile();
    this._checkServer();
    console.log('[App] Project Claw 小程序启动', this.globalData.clientId);
  },

  onShow() {
    this._checkServer();
  },

  // ─── 初始化客户端 ID ───
  _initClientId() {
    let id = wx.getStorageSync('claw_client_id');
    if (!id) {
      id = 'c_' + Date.now() + '_' + Math.random().toString(36).slice(2, 8);
      wx.setStorageSync('claw_client_id', id);
    }
    this.globalData.clientId = id;
  },

  // ─── 初始化画像 ───
  _initProfile() {
    const profile = ProfileManager.loadClientProfile(this.globalData.clientId);
    this.globalData.userProfile = profile;
  },

  // ─── 服务器健康检查 ───
  async _checkServer() {
    const request = createRequest(this.globalData.serverBase, this.globalData.token);
    const sysAPI = SystemAPI(request);
    try {
      const res = await sysAPI.health();
      this.globalData.isConnected = true;
      this.globalData.onlineMerchants = res.online_merchants || 0;
      this.globalData.serverVersion = res.version || '';
    } catch (e) {
      this.globalData.isConnected = false;
    }
  },

  // ─── 全局请求方法 ───
  request(opts) {
    return createRequest(this.globalData.serverBase, this.globalData.token)(opts);
  },
});
