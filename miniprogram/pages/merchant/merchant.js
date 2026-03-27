// pages/merchant/merchant.js - B端商家控制台 v2.0
const { createRequest, SystemAPI, ProfileAPI, DialogueAPI } = require('../../api/request');
const ProfileManager = require('../../utils/profile');

Page({
  data: {
    merchantId: 'box-001',
    profile: null,
    editProfile: null,
    stats: null,
    isOnline: false,
    isLoading: false,
    showProfileEdit: false,
    recentOffers: [],
    totalNegotiations: 0,
    totalRevenue: 0,
    successRate: 0,
    wsStatus: 'disconnected',
  },

  _sysAPI: null,
  _profileAPI: null,
  _pollTimer: null,

  onLoad() {
    const app = getApp();
    const request = createRequest(app.globalData.serverBase, app.globalData.token);
    this._sysAPI    = SystemAPI(request);
    this._profileAPI = ProfileAPI(request);
    this._dialogueAPI = DialogueAPI(request);

    const merchantId = wx.getStorageSync('claw_merchant_id') || 'box-001';
    const profile = ProfileManager.loadMerchantProfile(merchantId);
    this.setData({ merchantId, profile, editProfile: { ...profile } });
    this._loadStats();
    this._startPolling();
  },

  onShow() { this._loadStats(); },

  onUnload() { this._stopPolling(); },

  _startPolling() {
    this._stopPolling();
    this._pollTimer = setInterval(() => this._loadStats(), 15000);
  },

  _stopPolling() {
    if (this._pollTimer) { clearInterval(this._pollTimer); this._pollTimer = null; }
  },

  async _loadStats() {
    try {
      const res = await this._sysAPI.stats();
      const isOnline = (res.merchant_ids || []).includes(this.data.merchantId);
      const m = res.metrics || {};
      const total = m.execute_total || 0;
      const success = m.execute_success || 0;
      this.setData({
        stats: res,
        isOnline,
        totalNegotiations: m.intent_total || 0,
        successRate: total > 0 ? Math.round(success / total * 100) : 0,
        wsStatus: isOnline ? 'connected' : 'disconnected',
      });
    } catch (e) {
      console.warn('[Merchant] stats failed', e);
    }
  },

  async onSaveProfile() {
    const { editProfile, merchantId } = this.data;
    if (!editProfile.merchant_id) {
      wx.showToast({ title: '商家ID不能为空', icon: 'none' }); return;
    }
    this.setData({ isLoading: true });
    wx.showLoading({ title: '保存中...' });
    try {
      await this._profileAPI.upsertMerchantProfile(merchantId, editProfile);
      await this._dialogueAPI.upsertMerchantProfile(editProfile);
      ProfileManager.saveMerchantProfile(editProfile);
      this.setData({ profile: { ...editProfile }, showProfileEdit: false });
      wx.showToast({ title: '画像已更新', icon: 'success' });
    } catch (e) {
      // 网络失败时只保存本地
      ProfileManager.saveMerchantProfile(editProfile);
      this.setData({ profile: { ...editProfile }, showProfileEdit: false });
      wx.showToast({ title: '已本地保存', icon: 'none' });
    } finally {
      wx.hideLoading();
      this.setData({ isLoading: false });
    }
  },

  onEditField(e) {
    const key = e.currentTarget.dataset.key;
    const raw = e.detail.value;
    const numFields = ['bottom_price','normal_price','max_discount_rate',
      'delivery_time_minutes','quality_score','service_score'];
    const value = numFields.includes(key) ? parseFloat(raw) || 0 : raw;
    this.setData({ [`editProfile.${key}`]: value });
  },

  onSliderChange(e) {
    const key = e.currentTarget.dataset.key;
    const val = e.detail.value;
    const factor = ['max_discount_rate','quality_score','service_score'].includes(key) ? 100 : 1;
    this.setData({ [`editProfile.${key}`]: val / factor });
  },

  onToggleProfileEdit() {
    this.setData({
      showProfileEdit: !this.data.showProfileEdit,
      editProfile: { ...this.data.profile },
    });
  },

  onToggleOpen() {
    const is_open = !this.data.editProfile.is_open;
    this.setData({ 'editProfile.is_open': is_open });
    wx.showToast({ title: is_open ? '营业中' : '已打烊', icon: 'none' });
  },

  onChangeMerchantId() {
    wx.showModal({
      title: '修改商家ID',
      editable: true,
      placeholderText: '输入新的商家ID',
      content: this.data.merchantId,
      success: (res) => {
        if (res.confirm && res.content) {
          const newId = res.content.trim();
          wx.setStorageSync('claw_merchant_id', newId);
          this.setData({ merchantId: newId, 'editProfile.merchant_id': newId });
          wx.showToast({ title: '商家ID已更新', icon: 'success' });
        }
      },
    });
  },

  onRefreshStats() { this._loadStats(); },

  onCopyId(e) {
    wx.setClipboardData({
      data: e.currentTarget.dataset.id,
      success: () => wx.showToast({ title: '已复制', icon: 'success' }),
    });
  },
});
