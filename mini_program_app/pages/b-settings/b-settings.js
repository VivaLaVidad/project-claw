const {
  getMerchantId,
  clearMerchantToken,
  merchantDeviceStatus,
} = require('../../utils/b_api');
const { getBaseUrl, setBaseUrl, resetBaseUrl, BASE_URL_PRESETS } = require('../../utils/api');

Page({
  data: {
    merchantId: '',
    device: null,
    baseUrl: '',
    customBaseUrl: '',
  },

  onShow() {
    this.setData({ merchantId: getMerchantId(), baseUrl: getBaseUrl(), customBaseUrl: getBaseUrl() });
    this.refreshDevice();
  },

  async refreshDevice() {
    try {
      const device = await merchantDeviceStatus();
      this.setData({ device });
    } catch {}
  },

  onInputUrl(e) { this.setData({ customBaseUrl: e.detail.value }); },
  useTencent() { this.setData({ baseUrl: setBaseUrl(BASE_URL_PRESETS.tencent || BASE_URL_PRESETS.production) }); wx.showToast({ title: '已切腾讯云', icon: 'success' }); },
  useRailway() { this.setData({ baseUrl: setBaseUrl(BASE_URL_PRESETS.railway) }); wx.showToast({ title: '已切 Railway', icon: 'success' }); },
  useZeabur() { this.setData({ baseUrl: setBaseUrl(BASE_URL_PRESETS.zeabur) }); wx.showToast({ title: '已切 Zeabur', icon: 'success' }); },
  useLocal() { this.setData({ baseUrl: setBaseUrl(BASE_URL_PRESETS.local) }); wx.showToast({ title: '已切本地', icon: 'success' }); },
  useCustom() { this.setData({ baseUrl: setBaseUrl(this.data.customBaseUrl) }); wx.showToast({ title: '已切自定义', icon: 'success' }); },
  resetDefault() { this.setData({ baseUrl: resetBaseUrl() }); wx.showToast({ title: '已恢复默认', icon: 'success' }); },

  logout() {
    clearMerchantToken();
    wx.showToast({ title: '已退出', icon: 'success' });
    wx.navigateTo({ url: '/pages/b-dashboard/b-dashboard' });
  },
});
