/**
 * Project Claw v14.3 - pages/index/index.js
 * 首页：询价表单 + 位置获取 + 健康检测
 */
const { ensureToken, healthCheck, getOnlineMerchants, requestTrade, BASE_URL } = require('../../utils/api');

const DEFAULT_ITEMS = [
  '招牌牛肉面', '麻辣烫', '猪脚饭', '黄焖鸡米饭',
  '水饺', '凉皮肉夹馍', '烤肉饭', '沙拉',
  '叉烧饭', '锅贴', '部队锅', '煲仔饭',
];

Page({
  data: {
    loading: false,
    diagLoading: false,
    onlineMerchants: 0,
    healthStatus: '',
    healthOk: null,
    envBaseUrl: BASE_URL,
    buildTag: 'c-end-v14.3',
    geoStr: '',
    _geo: null,
    quickItems: DEFAULT_ITEMS,
    showAdvanced: false,
    form: {
      item_name: '',
      demand_text: '',
      max_price: '',
      quantity: '1',
      timeout_sec: '20',
    },
  },

  onLoad() {
    this._bootstrapPage();
  },

  async _bootstrapPage() {
    const app = getApp();
    this.setData({ buildTag: `c-end-v${(app.globalData && app.globalData.version) || '14.3.0'}` });
    const cid = await this._ensureClientId();
    await ensureToken(cid).catch(() => {});
    this._runDiagnostics();
  },

  _ensureClientId() {
    const app = getApp();
    const cached = app.globalData.clientId || wx.getStorageSync('claw_client_id');
    if (cached) {
      if (!app.globalData.clientId) app.globalData.clientId = cached;
      return Promise.resolve(cached);
    }

    return new Promise((resolve) => {
      wx.login({
        success: (res) => {
          const code = res && res.code ? res.code.slice(0, 12) : String(Date.now());
          const suffix = Math.random().toString(36).slice(2, 8);
          const clientId = `wx-${code}-${suffix}`;
          wx.setStorageSync('claw_client_id', clientId);
          app.globalData.clientId = clientId;
          resolve(clientId);
        },
        fail: () => {
          const clientId = `anon-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
          wx.setStorageSync('claw_client_id', clientId);
          app.globalData.clientId = clientId;
          resolve(clientId);
        },
      });
    });
  },

  onShow() {
    // 页面可见时重新诊断，避免冷启动瞬时网络抖动误判
    this._runDiagnostics();
  },

  // ─── 诊断 ────────────────────────────────────────────────────────────────
  async _runDiagnostics() {
    this.setData({ diagLoading: true });
    await Promise.allSettled([
      this._checkHealth(),
      this._refreshMerchants(),
    ]);
    this.setData({ diagLoading: false });
  },

  async _checkHealth() {
    try {
      const res = await healthCheck();
      this.setData({
        healthStatus: `正常 · ${res.merchants || 0} 家商家在线`,
        healthOk: true,
      });
    } catch (e) {
      const detail = (e && (e.detail || e.errMsg || e.message)) || 'network_error';
      this.setData({
        healthStatus: `服务暂不可用（${detail}）`,
        healthOk: false,
      });
    }
  },

  async _refreshMerchants() {
    const cache = getApp().getCacheManager && getApp().getCacheManager();
    const cachedOnline = cache && cache.get('online_merchants_count');
    if (typeof cachedOnline === 'number') {
      this.setData({ onlineMerchants: cachedOnline });
    }

    // 工业级：短重试，减少移动网络抖动造成的误判
    for (let i = 0; i < 3; i++) {
      try {
        const res = await getOnlineMerchants();
        const count = (res && res.online_merchants) || 0;
        this.setData({ onlineMerchants: count });
        if (cache) cache.set('online_merchants_count', count, 15000);
        return;
      } catch (e) {
        if (i === 2) {
          const detail = (e && (e.detail || e.errMsg || e.message)) || 'network_error';
          console.warn('[Index] getOnlineMerchants failed:', detail, 'base=', BASE_URL);
          try {
            const health = await healthCheck();
            const fallbackCount = (health && health.merchants) || 0;
            this.setData({ onlineMerchants: fallbackCount });
          } catch (_) {
            this.setData({ onlineMerchants: 0 });
          }
        }
      }
      await new Promise(r => setTimeout(r, 400));
    }
  },

  onTapDiag() { this._runDiagnostics(); },

  // ─── 位置 ────────────────────────────────────────────────────────────────
  getLocation() {
    wx.showLoading({ title: '获取位置中…' });
    wx.authorize({
      scope: 'scope.userLocation',
      success: () => {
        wx.getLocation({
          type: 'wgs84',
          success: (loc) => {
            wx.hideLoading();
            const geo = { lat: loc.latitude, lng: loc.longitude, radius_m: 1000 };
            this.setData({
              _geo: geo,
              geoStr: `${loc.latitude.toFixed(4)}, ${loc.longitude.toFixed(4)}`,
            });
            wx.showToast({ title: '位置已获取', icon: 'success' });
          },
          fail: () => { wx.hideLoading(); wx.showToast({ title: '获取位置失败', icon: 'none' }); },
        });
      },
      fail: () => {
        wx.hideLoading();
        wx.showModal({
          title: '需要位置权限',
          content: '请在设置中开启位置权限，以便筛选附近商家',
          confirmText: '去设置',
          success: (r) => { if (r.confirm) wx.openSetting(); },
        });
      },
    });
  },

  // ─── 快捷选品 ────────────────────────────────────────────────────────────
  onTapQuick(e) {
    const item = e.currentTarget.dataset.item;
    this.setData({
      'form.item_name': item,
      'form.demand_text': `我要${item}，实惠好吃`,
    });
  },

  // ─── 表单输入 ────────────────────────────────────────────────────────────
  onInput(e) {
    const key = e.currentTarget.dataset.key;
    let val = e.detail.value;
    // 价格和数量只允许正数
    if (key === 'max_price' || key === 'quantity') {
      val = val.replace(/[^0-9.]/g, '');
    }
    this.setData({ [`form.${key}`]: val });
    // 自动生成需求描述
    if (key === 'item_name' && val) {
      const price = this.data.form.max_price;
      this.setData({
        'form.demand_text': price ? `我要${val}，${price}元以内` : `我要${val}，实惠好吃`,
      });
    }
    if (key === 'max_price' && this.data.form.item_name) {
      const item = this.data.form.item_name;
      this.setData({ 'form.demand_text': `我要${item}，${val}元以内` });
    }
  },

  // ─── 提交询价 ────────────────────────────────────────────────────────────
  _validate() {
    const f = this.data.form;
    if (!f.item_name.trim())          return '请填写商品名称';
    if (!f.max_price || Number(f.max_price) <= 0) return '请填写有效预算';
    if (Number(f.max_price) > 9999)   return '预算请填写合理金额';
    return null;
  },

  async submitTrade() {
    if (this.data.loading) return;
    const errMsg = this._validate();
    if (errMsg) { wx.showToast({ title: errMsg, icon: 'none' }); return; }

    if (!this.data.healthOk) {
      const ok = await new Promise(resolve => {
        wx.showModal({
          title: '服务可能不可用',
          content: '当前服务状态异常，是否仍然发起询价？',
          confirmText: '继续',
          cancelText: '取消',
          success: r => resolve(r.confirm),
        });
      });
      if (!ok) return;
    }

    const app = getApp();
    const clientId = app.globalData.clientId || wx.getStorageSync('claw_client_id') || `anon-${Date.now()}`;
    await ensureToken(clientId).catch(() => {});

    const f = this.data.form;
    const payload = {
      request_id:  `r-${Date.now()}`,
      trace_id:    `trace-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      client_id:   clientId,
      item_name:   f.item_name.trim(),
      demand_text: f.demand_text.trim() || `我要${f.item_name.trim()}`,
      max_price:   Number(f.max_price),
      quantity:    Math.max(1, Number(f.quantity || 1)),
      timeout_sec: Math.min(30, Math.max(5, Number(f.timeout_sec || 20))),
    };
    if (this.data._geo) payload.location = this.data._geo;

    this.setData({ loading: true });
    wx.showLoading({ title: '正在询价…', mask: true });
    
    try {
      const bundle = await requestTrade(payload);
      app.globalData.currentTrade = { request: payload, bundle };
      this._saveLocalHistory(payload, bundle);
      wx.hideLoading();
      wx.navigateTo({ url: '/pages/offers/offers' });
    } catch (e) {
      wx.hideLoading();
      wx.showModal({
        title: '询价失败',
        content: String((e && e.detail) || '网络异常，请稍后重试'),
        showCancel: false,
      });
    } finally {
      this.setData({ loading: false });
    }
  },

  _saveLocalHistory(payload, bundle) {
    try {
      const history = wx.getStorageSync('claw_history') || [];
      history.unshift({
        request_id: payload.request_id,
        item_name:  payload.item_name,
        max_price:  payload.max_price,
        offer_count: (bundle.offers || []).length,
        ts: Date.now(),
      });
      wx.setStorageSync('claw_history', history.slice(0, 50));
    } catch {}
  },

  // ─── 高级选项折叠 ───────────────────────────────────────────────────────
  toggleAdvanced() {
    this.setData({ showAdvanced: !this.data.showAdvanced });
  },

  // ─── 导航 ────────────────────────────────────────────────────────────────
  goHistory() { wx.navigateTo({ url: '/pages/history/history' }); },
  goPrivacy()  { wx.navigateTo({ url: '/pages/privacy/privacy' }); },

  copyDebugInfo() {
    const app = getApp();
    const debug = {
      build: this.data.buildTag,
      baseUrl: this.data.envBaseUrl,
      health: this.data.healthStatus,
      onlineMerchants: this.data.onlineMerchants,
      clientId: app.globalData.clientId || wx.getStorageSync('claw_client_id') || '',
      ts: Date.now(),
    };
    wx.setClipboardData({
      data: JSON.stringify(debug),
      success: () => wx.showToast({ title: '诊断信息已复制', icon: 'success' }),
    });
  }
});
