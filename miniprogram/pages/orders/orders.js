// pages/orders/orders.js - 订单历史页
const { createRequest, DialogueAPI } = require('../../api/request');

Page({
  data: {
    orders: [],
    isLoading: false,
    activeSessionId: '',
    activeDetail: null,
  },

  _request: null,
  _dialogueAPI: null,

  onLoad() {
    const app = getApp();
    this._request = createRequest(app.globalData.serverBase, app.globalData.token);
    this._dialogueAPI = DialogueAPI(this._request);
    this._loadOrders();
  },

  onShow() {
    this._loadOrders();
  },

  async _loadOrders() {
    this.setData({ isLoading: true });
    try {
      const res = await this._request({ method: 'GET', path: '/orders?limit=50' });
      this.setData({ orders: res.items || [] });
    } catch (e) {
      console.error('[Orders] load failed', e);
      wx.showToast({ title: '加载失败', icon: 'none' });
    } finally {
      this.setData({ isLoading: false });
    }
  },

  async onTapOrder(e) {
    const { intentId } = e.currentTarget.dataset;
    if (this.data.activeSessionId === intentId) {
      this.setData({ activeSessionId: '', activeDetail: null });
      return;
    }
    this.setData({ activeSessionId: intentId, isLoading: true });
    try {
      const res = await this._request({ method: 'GET', path: `/orders/${intentId}` });
      this.setData({ activeDetail: res });
    } catch (e) {
      wx.showToast({ title: '获取详情失败', icon: 'none' });
    } finally {
      this.setData({ isLoading: false });
    }
  },

  onRefresh() {
    this._loadOrders();
  },

  formatTime(ts) {
    if (!ts) return '-';
    const d = new Date(ts * 1000);
    return `${d.getMonth()+1}/${d.getDate()} ${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`;
  },

  statusText(status) {
    const map = {
      created: '已创建', broadcasted: '广播中', executing: '执行中',
      executed: '已成交', failed: '失败',
    };
    return map[status] || status;
  },

  statusClass(status) {
    const map = {
      created: 'status-gray', broadcasted: 'status-blue',
      executing: 'status-orange', executed: 'status-green', failed: 'status-red',
    };
    return map[status] || 'status-gray';
  },
});
