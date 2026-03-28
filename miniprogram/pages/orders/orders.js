// pages/orders/orders.js - 订单历史页 v3.0（完整对齐后端 OrderRecord 结构）
const { createRequest, SystemAPI } = require('../../api/request');
const ProfileManager = require('../../utils/profile');

Page({
  data: {
    orders: [],
    isLoading: false,
    isOnline: true,
    activeIntentId: '',
    activeDetail: null,
    filterStatus: 'all',
    filteredOrders: [],
    totalCount: 0,
    executedCount: 0,
    totalSpend: 0,
  },

  _sysAPI: null,

  onLoad() {
    const app = getApp();
    const request = createRequest(app.globalData.serverBase, app.globalData.token);
    this._sysAPI = SystemAPI(request);
    this._loadOrders();
  },

  onShow()            { this._loadOrders(); },
  onPullDownRefresh() { this._loadOrders().finally(() => wx.stopPullDownRefresh()); },
  onRefresh()         { this._loadOrders(); },

  async _loadOrders() {
    this.setData({ isLoading: true });
    try {
      const res = await this._sysAPI.orders(100);
      const orders = Array.isArray(res) ? res : (res.items || []);
      orders.forEach(o => ProfileManager.saveLocalOrder(o));
      this.setData({ orders, isOnline: true });
      this._calcStats(orders);
      this._applyFilter();
    } catch (e) {
      const localOrders = ProfileManager.getLocalOrders();
      this.setData({ orders: localOrders, isOnline: false });
      this._calcStats(localOrders);
      this._applyFilter();
      if (localOrders.length === 0) wx.showToast({ title: '服务暂时不可用', icon: 'none' });
    } finally {
      this.setData({ isLoading: false });
    }
  },

  _calcStats(orders) {
    const executed = orders.filter(o => o.status === 'executed');
    const spend = executed.reduce((sum, o) => {
      return sum + (o.selected_offer ? Number(o.selected_offer.final_price) : 0);
    }, 0);
    this.setData({ totalCount: orders.length, executedCount: executed.length, totalSpend: spend });
  },

  onFilterChange(e) {
    this.setData({ filterStatus: e.currentTarget.dataset.status });
    this._applyFilter();
  },

  _applyFilter() {
    const { orders, filterStatus } = this.data;
    const filtered = filterStatus === 'all' ? orders : orders.filter(o => o.status === filterStatus);
    this.setData({ filteredOrders: filtered });
  },

  async onTapOrder(e) {
    const { intentId } = e.currentTarget.dataset;
    if (this.data.activeIntentId === intentId) {
      this.setData({ activeIntentId: '', activeDetail: null });
      return;
    }
    this.setData({ activeIntentId: intentId, activeDetail: null, isLoading: true });
    try {
      const res = await this._sysAPI.orderDetail(intentId);
      this.setData({ activeDetail: res });
    } catch (e) {
      const local = ProfileManager.getLocalOrders().find(o => o.intent_id === intentId);
      this.setData({ activeDetail: local || null });
    } finally {
      this.setData({ isLoading: false });
    }
  },

  onViewDialogue(e) {
    const { merchantId } = e.currentTarget.dataset;
    wx.navigateTo({
      url: `/pages/dialogue/dialogue?sessionId=&itemName=&merchantId=${merchantId || 'box-001'}`,
    });
  },

  onCopyId(e) {
    const { id } = e.currentTarget.dataset;
    wx.setClipboardData({ data: id, success: () => wx.showToast({ title: '已复制', icon: 'success' }) });
  },

  formatTime(ts) { return ProfileManager.formatTime(ts); },
  statusText(s)  { return ProfileManager.statusText(s); },
  statusClass(s) { return ProfileManager.statusClass(s); },
});
