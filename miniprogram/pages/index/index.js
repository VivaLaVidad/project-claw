// pages/index/index.js - C端发现页
const { createRequest, DialogueAPI, IntentAPI } = require('../../api/request');
const ProfileManager = require('../../utils/profile');

Page({
  data: {
    itemName: '',
    expectedPrice: '',
    isLoading: false,
    serverStatus: 'unknown',  // 'online' | 'offline' | 'unknown'
    recentOffers: [],
    profile: null,
    showProfilePanel: false,
  },

  onLoad() {
    const app = getApp();
    const profile = ProfileManager.loadClientProfile(app.globalData.clientId);
    this.setData({ profile });
    this._checkServerStatus();
  },

  onShow() {
    this._checkServerStatus();
  },

  // ─── UI 事件 ───

  onItemNameInput(e) {
    this.setData({ itemName: e.detail.value });
  },

  onPriceInput(e) {
    this.setData({ expectedPrice: e.detail.value });
  },

  onToggleProfile() {
    this.setData({ showProfilePanel: !this.data.showProfilePanel });
  },

  onProfileChange(e) {
    const key = e.currentTarget.dataset.key;
    const value = parseFloat(e.detail.value);
    const profile = { ...this.data.profile, [key]: value };
    this.setData({ profile });
    ProfileManager.saveClientProfile(profile);
  },

  // ─── 核心：发起 A2A 对话 ───

  async onStartDialogue() {
    const { itemName, expectedPrice, isLoading } = this.data;
    if (isLoading) return;
    if (!itemName.trim()) {
      wx.showToast({ title: '请输入商品名', icon: 'none' }); return;
    }
    const price = parseFloat(expectedPrice);
    if (!price || price <= 0) {
      wx.showToast({ title: '请输入有效预算', icon: 'none' }); return;
    }

    const app = getApp();
    const request = createRequest(app.globalData.serverBase, app.globalData.token);
    const dialogueAPI = DialogueAPI(request);

    this.setData({ isLoading: true });
    wx.showLoading({ title: '正在联系商家...' });

    try {
      // 1. 上传个性化画像
      await dialogueAPI.upsertClientProfile({
        ...this.data.profile,
        client_id: app.globalData.clientId,
      });

      // 2. 构造 intent
      const intent = ProfileManager.buildIntent(
        app.globalData.clientId,
        itemName.trim(),
        price,
      );

      // 3. 发起对话
      const merchantId = app.globalData.merchantId || 'box-001';
      const res = await dialogueAPI.start({
        intent,
        merchantId,
        openingText: `预算${price}元，能给我最优惠的${itemName}方案吗？`,
      });

      wx.hideLoading();
      this.setData({ isLoading: false });

      // 4. 跳转对话页
      wx.navigateTo({
        url: `/pages/dialogue/dialogue?sessionId=${res.session_id}&itemName=${encodeURIComponent(itemName)}&merchantId=${merchantId}`,
      });
    } catch (err) {
      wx.hideLoading();
      this.setData({ isLoading: false });
      console.error('[Index] start dialogue failed:', err);
      wx.showToast({ title: err.msg || '启动失败，请检查服务', icon: 'none' });
    }
  },

  // ─── 意图广播（快速模式）───

  async onBroadcastIntent() {
    const { itemName, expectedPrice, isLoading } = this.data;
    if (isLoading) return;
    if (!itemName.trim() || !parseFloat(expectedPrice)) {
      wx.showToast({ title: '请填写商品和预算', icon: 'none' }); return;
    }
    const app = getApp();
    const request = createRequest(app.globalData.serverBase, app.globalData.token);
    const intentAPI = IntentAPI(request);

    this.setData({ isLoading: true });
    wx.showLoading({ title: '广播中...' });

    try {
      const res = await intentAPI.broadcast({
        clientId: app.globalData.clientId,
        location: '小程序',
        demandText: `想要${itemName.trim()}`,
        maxPrice: parseFloat(expectedPrice),
        timeout: 3.0,
      });
      wx.hideLoading();
      this.setData({ isLoading: false, recentOffers: res.offers || [] });
      if (!res.offers || res.offers.length === 0) {
        wx.showToast({ title: '暂无商家响应', icon: 'none' });
      }
    } catch (err) {
      wx.hideLoading();
      this.setData({ isLoading: false });
      wx.showToast({ title: err.msg || '广播失败', icon: 'none' });
    }
  },

  // ─── 检查服务状态 ───

  async _checkServerStatus() {
    const app = getApp();
    const request = createRequest(app.globalData.serverBase, app.globalData.token);
    try {
      await request({ method: 'GET', path: '/health', timeout: 4000 });
      this.setData({ serverStatus: 'online' });
      app.globalData.isConnected = true;
    } catch (e) {
      this.setData({ serverStatus: 'offline' });
      app.globalData.isConnected = false;
    }
  },
});
