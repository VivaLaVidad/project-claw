// pages/merchant/merchant.js - B端商家控制台
const { createRequest, DialogueAPI } = require('../../api/request');
const ProfileManager = require('../../utils/profile');

Page({
  data: {
    merchantId: 'box-001',
    profile: null,
    stats: null,
    isOnline: false,
    isLoading: false,
    showProfileEdit: false,
    editProfile: null,
  },

  _request: null,
  _dialogueAPI: null,

  onLoad() {
    const app = getApp();
    this._request = createRequest(app.globalData.serverBase, app.globalData.token);
    this._dialogueAPI = DialogueAPI(this._request);

    const merchantId = wx.getStorageSync('merchant_id') || 'box-001';
    const profile = ProfileManager.loadMerchantProfile(merchantId);
    this.setData({ merchantId, profile, editProfile: { ...profile } });
    this._loadStats();
  },

  onShow() {
    this._loadStats();
  },

  // ─── 加载服务统计 ───

  async _loadStats() {
    try {
      const res = await this._request({ method: 'GET', path: '/stats', timeout: 5000 });
      const isOnline = (res.merchant_ids || []).includes(this.data.merchantId);
      this.setData({ stats: res, isOnline });
    } catch (e) {
      console.warn('[Merchant] stats load failed', e);
    }
  },

  // ─── 保存 B 端画像 ───

  async onSaveProfile() {
    const { editProfile } = this.data;
    if (!editProfile.merchant_id) {
      wx.showToast({ title: '商家ID不能为空', icon: 'none' }); return;
    }
    this.setData({ isLoading: true });
    wx.showLoading({ title: '保存中...' });
    try {
      await this._dialogueAPI.upsertMerchantProfile(editProfile);
      ProfileManager.saveMerchantProfile(editProfile);
      this.setData({ profile: { ...editProfile }, showProfileEdit: false });
      wx.showToast({ title: '画像已更新', icon: 'success' });
    } catch (e) {
      wx.showToast({ title: e.msg || '保存失败', icon: 'none' });
    } finally {
      wx.hideLoading();
      this.setData({ isLoading: false });
    }
  },

  // ─── 字段编辑 ───

  onEditField(e) {
    const key = e.currentTarget.dataset.key;
    const raw = e.detail.value;
    const value = ['bottom_price','normal_price','max_discount_rate',
      'delivery_time_minutes','quality_score','service_score'].includes(key)
      ? parseFloat(raw) : raw;
    this.setData({ [`editProfile.${key}`]: value });
  },

  onToggleProfileEdit() {
    this.setData({
      showProfileEdit: !this.data.showProfileEdit,
      editProfile: { ...this.data.profile },
    });
  },

  onRefreshStats() {
    this._loadStats();
  },
});
