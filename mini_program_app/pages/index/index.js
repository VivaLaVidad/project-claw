/**
 * Project Claw v14.3 - pages/index/index.js
 * 首页：询价表单 + 位置获取 + 健康检测
 */
const { ensureToken, healthCheck, getOnlineMerchants, requestTrade, getBaseUrl } = require('../../utils/api');

function tryParseJsonText(value) {
  if (typeof value !== 'string') return value;
  const text = value.trim();
  if (!text) return value;
  if ((text.startsWith('{') && text.endsWith('}')) || (text.startsWith('[') && text.endsWith(']'))) {
    try {
      return JSON.parse(text);
    } catch (_) {
      return value;
    }
  }
  return value;
}

function extractMerchantCount(value, depth = 0) {
  if (depth > 4 || value == null) return 0;

  const parsed = tryParseJsonText(value);

  if (typeof parsed === 'number') {
    return Number.isFinite(parsed) && parsed > 0 ? parsed : 0;
  }

  if (Array.isArray(parsed)) {
    return parsed.length;
  }

  if (typeof parsed !== 'object') return 0;

  const directCount = Number(
    parsed.online_merchants ??
    parsed.merchants ??
    parsed.onlineMerchantsCount ??
    parsed.count ??
    parsed.total
  );
  if (Number.isFinite(directCount) && directCount > 0) return directCount;

  if (Array.isArray(parsed.items)) return parsed.items.length;
  if (Array.isArray(parsed.onlineMerchants)) return parsed.onlineMerchants.length;
  if (Array.isArray(parsed.merchants_list)) return parsed.merchants_list.length;

  const nestedKeys = ['data', 'result', 'payload', 'body', 'response'];
  for (const key of nestedKeys) {
    if (parsed[key] != null) {
      const nestedCount = extractMerchantCount(parsed[key], depth + 1);
      if (nestedCount > 0) return nestedCount;
    }
  }

  for (const key of Object.keys(parsed)) {
    const nested = parsed[key];
    if (nested && typeof nested === 'object') {
      const nestedCount = extractMerchantCount(nested, depth + 1);
      if (nestedCount > 0) return nestedCount;
    }
  }

  return 0;
}

function resolveMerchantCount(res) {
  return extractMerchantCount(res, 0);
}

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
    envBaseUrl: getBaseUrl(),
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
    this.setData({ envBaseUrl: getBaseUrl() });
    this._runDiagnostics();
  },

  async _runDiagnostics() {
    this.setData({ diagLoading: true, envBaseUrl: getBaseUrl() });
    await Promise.allSettled([
      this._checkHealth(),
      this._refreshMerchants(),
    ]);
    this.setData({ diagLoading: false, envBaseUrl: getBaseUrl() });
  },

  async _checkHealth() {
    try {
      const res = await healthCheck();
      console.log('[Index] healthCheck raw =', res);
      const count = resolveMerchantCount(res);
      console.log('[Index] healthCheck count =', count);
      const nextState = {
        healthStatus: `正常 · ${count} 家商家在线`,
        healthOk: true,
      };
      const cache = getApp().getCacheManager && getApp().getCacheManager();
      if (count > 0) {
        nextState.onlineMerchants = count;
        if (cache) cache.set('online_merchants_count', count, 15000);
      }
      this.setData(Object.assign(nextState, { envBaseUrl: getBaseUrl() }));
    } catch (e) {
      const detail = (e && (e.detail || e.errMsg || e.message)) || 'network_error';
      this.setData({
        healthStatus: `服务暂不可用（${detail}）`,
        healthOk: false,
        envBaseUrl: getBaseUrl(),
      });
    }
  },

  async _refreshMerchants() {
    const cache = getApp().getCacheManager && getApp().getCacheManager();
    const cachedOnline = cache && cache.get('online_merchants_count');
    if (typeof cachedOnline === 'number') {
      this.setData({ onlineMerchants: cachedOnline });
    }

    for (let i = 0; i < 3; i++) {
      try {
        const res = await getOnlineMerchants();
        console.log('[Index] getOnlineMerchants raw =', res);
        const count = resolveMerchantCount(res);
        console.log('[Index] getOnlineMerchants count =', count);
        this.setData({ onlineMerchants: count, envBaseUrl: getBaseUrl() });
        if (cache) cache.set('online_merchants_count', count, 15000);
        return;
      } catch (e) {
        if (i === 2) {
          const detail = (e && (e.detail || e.errMsg || e.message)) || 'network_error';
          console.warn('[Index] getOnlineMerchants failed:', detail, 'base=', getBaseUrl());
          try {
            const health = await healthCheck();
            const fallbackCount = resolveMerchantCount(health);
            console.log('[Index] fallback health raw =', health);
            console.log('[Index] fallback health count =', fallbackCount);
            this.setData({ onlineMerchants: fallbackCount, envBaseUrl: getBaseUrl() });
          } catch (_) {
            this.setData({ onlineMerchants: 0, envBaseUrl: getBaseUrl() });
          }
        }
      }
      await new Promise(r => setTimeout(r, 400));
    }
  },

  onTapDiag() { this._runDiagnostics(); },

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

  onTapQuick(e) {
    const item = e.currentTarget.dataset.item;
    this.setData({
      'form.item_name': item,
      'form.demand_text': `我要${item}，实惠好吃`,
    });
  },

  onInput(e) {
    const key = e.currentTarget.dataset.key;
    let val = e.detail.value;
    if (key === 'max_price' || key === 'quantity') {
      val = val.replace(/[^0-9.]/g, '');
    }
    this.setData({ [`form.${key}`]: val });
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

  _validate() {
    const f = this.data.form;
    if (!f.item_name.trim()) return '请填写商品名称';
    if (!f.max_price || Number(f.max_price) <= 0) return '请填写有效预算';
    if (Number(f.max_price) > 9999) return '预算请填写合理金额';
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
      request_id: `r-${Date.now()}`,
      trace_id: `trace-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      client_id: clientId,
      item_name: f.item_name.trim(),
      demand_text: f.demand_text.trim() || `我要${f.item_name.trim()}`,
      max_price: Number(f.max_price),
      quantity: Math.max(1, Number(f.quantity || 1)),
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
        content: (e && (e.detail || e.errMsg || e.message)) || 'network_error',
        showCancel: false,
      });
    } finally {
      this.setData({ loading: false });
    }
  },

  _saveLocalHistory(payload, bundle) {
    try {
      const list = wx.getStorageSync('claw_history') || [];
      list.unshift({
        id: payload.request_id,
        item_name: payload.item_name,
        max_price: payload.max_price,
        created_at: Date.now(),
        offers: (bundle && bundle.offers) || [],
      });
      wx.setStorageSync('claw_history', list.slice(0, 30));
    } catch (_) {}
  },

  toggleAdvanced() {
    this.setData({ showAdvanced: !this.data.showAdvanced });
  },

  goHistory() { wx.navigateTo({ url: '/pages/history/history' }); },
  goPrivacy() { wx.navigateTo({ url: '/pages/privacy/privacy' }); },
  goBDashboard() { wx.navigateTo({ url: '/pages/b-dashboard/b-dashboard' }); },

  copyDebugInfo() {
    const debug = JSON.stringify({
      build: this.data.buildTag,
      base: this.data.envBaseUrl,
      health: this.data.healthStatus,
      online: this.data.onlineMerchants,
      geo: this.data.geoStr,
    }, null, 2);
    wx.setClipboardData({ data: debug, success: () => wx.showToast({ title: '诊断信息已复制', icon: 'success' }) });
  },
});



