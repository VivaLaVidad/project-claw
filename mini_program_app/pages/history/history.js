/**
 * Project Claw v14.3 - pages/history/history.js
 * 历史订单页：优先读本地缓存，后台同步云端
 */
const { ensureToken, getOrderHistory } = require('../../utils/api');

Page({
  data: {
    loading: false,
    items: [],
    empty: false,
    clientId: '',
  },

  onShow() {
    const app = getApp();
    const clientId = app.globalData.clientId || wx.getStorageSync('claw_client_id') || '';
    this.setData({ clientId });
    // 先展示本地缓存，再拉云端
    this._loadLocal();
    this._loadCloud(clientId);
  },

  _loadLocal() {
    try {
      const local = wx.getStorageSync('claw_history') || [];
      if (local.length) this.setData({ items: this._normalizeItems(local), empty: false });
    } catch {}
  },

  _normalizeItems(items = []) {
    return items.map((item) => ({
      ...item,
      displayTime: this.formatTime(item.ts),
      shortRequestId: item.request_id ? String(item.request_id).slice(-8) : '',
    }));
  },

  async _loadCloud(clientId) {
    if (!clientId) return;
    this.setData({ loading: true });
    try {
      await ensureToken(clientId);
      const res = await getOrderHistory(30);
      const items = (res && res.items) || [];
      if (items.length) {
        const normalized = this._normalizeItems(items);
        this.setData({ items: normalized, empty: false });
        wx.setStorageSync('claw_history', items.slice(0, 50));
      } else if (!this.data.items.length) {
        this.setData({ empty: true });
      }
    } catch {
      // 云端拉取失败不影响本地数据展示
    } finally {
      this.setData({ loading: false });
    }
  },

  onPullDownRefresh() {
    this._loadCloud(this.data.clientId).finally(() => {
      wx.stopPullDownRefresh();
    });
  },

  formatTime(ts) {
    if (!ts) return '';
    const d = new Date(ts);
    const pad = n => String(n).padStart(2, '0');
    return `${d.getMonth() + 1}/${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
  },

  backHome() { wx.reLaunch({ url: '/pages/index/index' }); },
});
