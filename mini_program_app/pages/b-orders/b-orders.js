const { merchantOrders } = require('../../utils/b_api');

Page({
  data: {
    items: [],
    loading: false,
    status: '',
    statuses: ['', 'pending', 'accepted', 'executed', 'failed'],
  },

  onShow() { this.refresh(); },

  async refresh() {
    this.setData({ loading: true });
    try {
      const res = await merchantOrders(50, this.data.status);
      this.setData({ items: res.items || [] });
    } catch (e) {
      wx.showToast({ title: String(e.detail || '加载失败'), icon: 'none' });
    } finally {
      this.setData({ loading: false });
    }
  },

  onStatusChange(e) {
    const idx = Number(e.detail.value || 0);
    this.setData({ status: this.data.statuses[idx] }, () => this.refresh());
  },
});
