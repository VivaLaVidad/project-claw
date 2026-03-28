// app.js - Project Claw 小程序全局入口 v3.0
// 工业级改进：环境切换/网络监听/全局错误处理/启动性能优化
const { createRequest, SystemAPI } = require('./api/request');
const ProfileManager = require('./utils/profile');

// ── 环境配置（修改 ENV 切换环境）────────────────────────────
const ENV = 'dev'; // 'dev' | 'prod'
const ENV_CONFIG = {
  dev: {
    serverBase: 'http://127.0.0.1:8765',
    wsBase:     'ws://127.0.0.1:8765',
    siriBase:   'http://127.0.0.1:8010',
  },
  prod: {
    serverBase: 'https://project-claw-production.up.railway.app',
    wsBase:     'wss://project-claw-production.up.railway.app',
    siriBase:   'https://project-claw-production.up.railway.app',
  },
};

App({
  globalData: {
    env:             ENV,
    clientId:        '',
    merchantId:      'box-001',
    userProfile:     null,
    serverBase:      ENV_CONFIG[ENV].serverBase,
    wsBase:          ENV_CONFIG[ENV].wsBase,
    siriBase:        ENV_CONFIG[ENV].siriBase,
    token:           '',
    isConnected:     false,
    networkType:     'unknown',
    serverVersion:   '',
    onlineMerchants: 0,
    lastHealthCheck: 0,
  },

  onLaunch() {
    this._initClientId();
    this._initProfile();
    this._checkServer();
    this._listenNetwork();
    console.log('[App] Project Claw 启动', {
      env:      ENV,
      clientId: this.globalData.clientId,
      server:   this.globalData.serverBase,
    });
  },

  onShow() {
    // 超过 30s 未检查时重新检查
    const now = Date.now();
    if (now - this.globalData.lastHealthCheck > 30000) {
      this._checkServer();
    }
  },

  // ── 初始化客户端 ID（持久化）────────────────────────────────
  _initClientId() {
    let id = wx.getStorageSync('claw_client_id');
    if (!id || typeof id !== 'string' || id.length < 8) {
      id = 'c_' + Date.now() + '_' + Math.random().toString(36).slice(2, 8);
      wx.setStorageSync('claw_client_id', id);
    }
    this.globalData.clientId = id;
  },

  // ── 初始化画像 ──────────────────────────────────────────────
  _initProfile() {
    const profile = ProfileManager.loadClientProfile(this.globalData.clientId);
    this.globalData.userProfile = profile;
  },

  // ── 服务器健康检查 ──────────────────────────────────────────
  async _checkServer() {
    this.globalData.lastHealthCheck = Date.now();
    const request = createRequest(this.globalData.serverBase, this.globalData.token);
    const sysAPI  = SystemAPI(request);
    try {
      const res = await sysAPI.health();
      this.globalData.isConnected     = true;
      this.globalData.onlineMerchants = res.online_merchants || 0;
      this.globalData.serverVersion   = res.version || '';
    } catch (e) {
      this.globalData.isConnected = false;
      console.warn('[App] 服务器不可达:', e.msg || e);
    }
  },

  // ── 网络状态监听 ────────────────────────────────────────────
  _listenNetwork() {
    wx.getNetworkType({
      success: (res) => { this.globalData.networkType = res.networkType; },
    });
    wx.onNetworkStatusChange((res) => {
      this.globalData.networkType = res.networkType;
      if (res.isConnected) {
        this._checkServer();
      } else {
        this.globalData.isConnected = false;
      }
    });
  },

  // ── 全局请求方法 ────────────────────────────────────────────
  request(opts) {
    return createRequest(this.globalData.serverBase, this.globalData.token)(opts);
  },

  // ── 切换环境（调试用）───────────────────────────────────────
  switchEnv(env) {
    if (!ENV_CONFIG[env]) return;
    this.globalData.env        = env;
    this.globalData.serverBase = ENV_CONFIG[env].serverBase;
    this.globalData.wsBase     = ENV_CONFIG[env].wsBase;
    this.globalData.siriBase   = ENV_CONFIG[env].siriBase;
    this._checkServer();
    console.log('[App] 切换环境:', env);
  },
});
