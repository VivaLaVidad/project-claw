// pages/orders/orders.js - 订单历史页 v2.0
const { createRequest, SystemAPI } = require('../../api/request');
const ProfileManager = require('../../utils/profile');

Page({
  data: {
    orders: [],
    localOrders: [],
    isLoading: false,
    activeIntentId: '',
    activeDetail: null,
    isOnline: true,
    filterStatus: 'all',
    filteredOrders: [],
  },

  _sysAPI: null,

  onLoad() {
    const app = getApp();
    const request = createRequest(app.globalData.serverBase, app.globalData.token);
    this._sysAPI = SystemAPI(request);
    this._loadOrders();
  },

  onShow() {
    this._loadOrders();
  },

  onPullDownRefresh() {
    this._loadOrders().then(() => wx.stopPullDownRefresh());
  },

  async _loadOrders() {
    this.setData({ isLoading: true });
    try {
      const res = await this._sysAPI.orders(100);
      const orders = res.items || [];
      this.setData({ orders, isOnline: true });
      this._applyFilter();
    } catch (e) {
      // 后端离线时显示本地缓存
      const localOrders = ProfileManager.getLocalOrders();
      this.setData({ orders: localOrders, isOnline: false });
      this._applyFilter();
      if (localOrders.length === 0) {
        wx.showToast({ title: '服务暂时不可用', icon: 'none' });
      }
    } finally {
      this.setData({ isLoading: false });
    }
  },

  onFilterChange(e) {
    this.setData({ filterStatus: e.currentTarget.dataset.status });
    this._applyFilter();
  },

  _applyFilter() {
    const { orders, filterStatus } = this.data;
    const filtered = filterStatus === 'all'
      ? orders
      : orders.filter(o => o.status === filterStatus);
    this.setData({ filteredOrders: filtered });
  },

  async onTapOrder(e) {
    const { intentId } = e.currentTarget.dataset;
    if (this.data.activeIntentId === intentId) {
      this.setData({ activeIntentId: '', activeDetail: null });
      return;
    }
    this.setData({ activeIntentId: intentId, isLoading: true });
    try {
      const res = await this._sysAPI.orderDetail(intentId);
      this.setData({ activeDetail: res });
    } catch (e) {
      wx.showToast({ title: '获取详情失败', icon: 'none' });
    } finally {
      this.setData({ isLoading: false });
    }
  },

  onRefresh() { this._loadOrders(); },

  onCopyId(e) {
    const { id } = e.currentTarget.dataset;
    wx.setClipboardData({ data: id, success: () => wx.showToast({ title: '已复制', icon: 'success' }) });
  },

  // wxs 无法用，直接在 js 里暴露格式化方法到 data
  formatTime(ts) { return ProfileManager.formatTime(ts); },
  statusText(s)  { return ProfileManager.statusText(s); },
  statusClass(s) { return ProfileManager.statusClass(s); },
});
