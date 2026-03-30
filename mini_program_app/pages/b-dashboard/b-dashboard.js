const {
  getMerchantToken,
  getMerchantId,
  merchantLogin,
  merchantDashboard,
  merchantSetAccepting,
} = require('../../utils/b_api');

Page({
  data: {
    merchant_id: '',
    merchant_key: '',
    promoter_id: '',
    loggingIn: false,
    ready: false,
    dashboard: null,
  },

  onLoad() {
    this.setData({ merchant_id: getMerchantId() || '' });
    if (getMerchantToken()) this.refreshDashboard();
  },

  onShow() {
    if (getMerchantToken()) this.refreshDashboard();
  },

  onInput(e) {
    this.setData({ [e.currentTarget.dataset.key]: e.detail.value });
  },

  async loginMerchant() {
    if (this.data.loggingIn) return;
    if (!this.data.merchant_id || !this.data.merchant_key) {
      wx.showToast({ title: '请填写商家ID和密钥', icon: 'none' });
      return;
    }
    this.setData({ loggingIn: true });
    try {
      await merchantLogin(this.data.merchant_id.trim(), this.data.merchant_key.trim(), this.data.promoter_id.trim());
      wx.showToast({ title: '登录成功', icon: 'success' });
      this.refreshDashboard();
    } catch (e) {
      wx.showModal({ title: '登录失败', content: String(e.detail || 'merchant_auth_failed'), showCancel: false });
    } finally {
      this.setData({ loggingIn: false });
    }
  },

  async refreshDashboard() {
    try {
      const data = await merchantDashboard();
      this.setData({ dashboard: data, ready: true });
    } catch (e) {
      this.setData({ ready: false });
      wx.showToast({ title: String(e.detail || '拉取失败'), icon: 'none' });
    }
  },

  async toggleAccepting(e) {
    try {
      await merchantSetAccepting(!!e.detail.value);
      this.refreshDashboard();
    } catch (err) {
      wx.showToast({ title: String(err.detail || '更新失败'), icon: 'none' });
    }
  },

  goOrders() { wx.navigateTo({ url: '/pages/b-orders/b-orders' }); },
  goWallet() { wx.navigateTo({ url: '/pages/b-wallet/b-wallet' }); },
  goSettings() { wx.navigateTo({ url: '/pages/b-settings/b-settings' }); },
});
