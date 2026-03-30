const { merchantWallet, merchantDashboard } = require('../../utils/b_api');

Page({
  data: {
    wallet: null,
    dashboard: null,
    loading: false,
  },

  onShow() { this.refresh(); },

  async refresh() {
    this.setData({ loading: true });
    try {
      const [wallet, dashboard] = await Promise.all([merchantWallet(), merchantDashboard()]);
      this.setData({ wallet, dashboard });
    } catch (e) {
      wx.showToast({ title: String(e.detail || '加载失败'), icon: 'none' });
    } finally {
      this.setData({ loading: false });
    }
  },
});
