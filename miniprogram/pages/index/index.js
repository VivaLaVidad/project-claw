// pages/index/index.js - C端发现页（B/C Agent 全自动谈判版）
const { createRequest, DialogueAPI, IntentAPI, AgentNegotiationAPI } = require('../../api/request');
const ProfileManager = require('../../utils/profile');

Page({
  data: {
    itemName: '',
    expectedPrice: '',
    isLoading: false,
    serverStatus: 'unknown',
    recentOffers: [],
    profile: null,
    showProfilePanel: false,
    // 全自动谈判状态
    autoNegotiating: false,
    negotiationLog: [],   // 实时谈判日志
    negotiationResult: null,
  },

  _pollTimer: null,

  onLoad() {
    const app = getApp();
    const profile = ProfileManager.loadClientProfile(app.globalData.clientId);
    this.setData({ profile });
    this._checkServerStatus();
  },

  onShow() {
    this._checkServerStatus();
  },

  onUnload() {
    if (this._pollTimer) clearInterval(this._pollTimer);
  },

  // ─── UI 事件 ───
  onItemNameInput(e) { this.setData({ itemName: e.detail.value }); },
  onPriceInput(e)    { this.setData({ expectedPrice: e.detail.value }); },
  onToggleProfile()  { this.setData({ showProfilePanel: !this.data.showProfilePanel }); },

  onProfileChange(e) {
    const key = e.currentTarget.dataset.key;
    const raw = parseFloat(e.detail.value);
    // price_sensitivity / time_urgency 滑块是 0-100，需转回 0-1
    const value = ['price_sensitivity', 'time_urgency', 'quality_preference'].includes(key)
      ? raw / 100 : raw;
    const profile = { ...this.data.profile, [key]: value };
    this.setData({ profile });
    ProfileManager.saveClientProfile(profile);
  },

  // ─── 核心 1：B/C Agent 全自动谈判 ───
  async onAutoNegotiate() {
    const { itemName, expectedPrice, isLoading, autoNegotiating } = this.data;
    if (isLoading || autoNegotiating) return;
    if (!itemName.trim()) { wx.showToast({ title: '请输入商品名', icon: 'none' }); return; }
    const price = parseFloat(expectedPrice);
    if (!price || price <= 0) { wx.showToast({ title: '请输入有效预算', icon: 'none' }); return; }

    const app = getApp();
    const request = createRequest(app.globalData.serverBase, app.globalData.token);
    const dialogueAPI = DialogueAPI(request);
    const agentAPI = AgentNegotiationAPI(request);

    this.setData({ isLoading: true, autoNegotiating: true, negotiationLog: [], negotiationResult: null });
    wx.showLoading({ title: 'Agent 正在谈判中...' });

    try {
      // 1. 上传 C端个性化画像
      await dialogueAPI.upsertClientProfile({
        ...this.data.profile,
        client_id: app.globalData.clientId,
      });
      this._addLog('info', '📋 C端画像已上传');

      // 2. 启动全自动谈判（B端Agent自动响应）
      const intentRes = await agentAPI.startAutoNegotiation({
        clientId: app.globalData.clientId,
        itemName: itemName.trim(),
        expectedPrice: price,
        maxDistanceKm: 8.0,
      });
      this._addLog('agent', `🤖 意图已广播，Intent ID: ${intentRes.intent_id || '-'}`);

      const intentId = intentRes.intent_id;

      // 3. 若后端返回直接结果（offer）
      if (intentRes.offers && intentRes.offers.length > 0) {
        wx.hideLoading();
        this.setData({ isLoading: false, recentOffers: intentRes.offers });
        this._addLog('deal', `✅ B端Agent已返回 ${intentRes.offers.length} 个报价`);
        this._showBestOffer(intentRes.offers[0], itemName);
        return;
      }

      // 4. 若需要轮询（异步谈判模式）
      if (intentId) {
        this._addLog('info', '⏳ B端Agent正在与各商家协商...');
        let polls = 0;
        this._pollTimer = setInterval(async () => {
          polls++;
          try {
            const result = await agentAPI.pollResult(intentId);
            if (result.status === 'completed' && result.best_offer) {
              clearInterval(this._pollTimer);
              wx.hideLoading();
              this.setData({
                isLoading: false,
                autoNegotiating: false,
                recentOffers: result.offers || [result.best_offer],
                negotiationResult: result.best_offer,
              });
              this._addLog('deal', `✅ 成交！¥${result.best_offer.final_price}`);
              this._showBestOffer(result.best_offer, itemName);
            } else if (result.status === 'failed' || polls > 20) {
              clearInterval(this._pollTimer);
              wx.hideLoading();
              this.setData({ isLoading: false, autoNegotiating: false });
              wx.showToast({ title: '暂无匹配商家', icon: 'none' });
            } else {
              this._addLog('agent', `🔄 第${polls}轮协商中...`);
            }
          } catch (e) {
            clearInterval(this._pollTimer);
            wx.hideLoading();
            this.setData({ isLoading: false, autoNegotiating: false });
          }
        }, 1500);
        return;
      }

      // 5. 降级：无 intentId，跳转标准对话页
      wx.hideLoading();
      this.setData({ isLoading: false, autoNegotiating: false });
      this._fallbackToDialogue(itemName, price);

    } catch (err) {
      wx.hideLoading();
      this.setData({ isLoading: false, autoNegotiating: false });
      console.error('[Index] auto negotiate failed:', err);
      // 降级到标准对话
      this._addLog('warn', '⚠️ 自动谈判失败，切换手动模式');
      this._fallbackToDialogue(itemName, price);
    }
  },

  // ─── 核心 2：发起 A2A 对话（手动模式）───
  async onStartDialogue() {
    const { itemName, expectedPrice, isLoading } = this.data;
    if (isLoading) return;
    if (!itemName.trim()) { wx.showToast({ title: '请输入商品名', icon: 'none' }); return; }
    const price = parseFloat(expectedPrice);
    if (!price || price <= 0) { wx.showToast({ title: '请输入有效预算', icon: 'none' }); return; }
    this._fallbackToDialogue(itemName, price);
  },

  async _fallbackToDialogue(itemName, price) {
    const app = getApp();
    const request = createRequest(app.globalData.serverBase, app.globalData.token);
    const dialogueAPI = DialogueAPI(request);
    this.setData({ isLoading: true });
    wx.showLoading({ title: '正在联系商家...' });
    try {
      await dialogueAPI.upsertClientProfile({ ...this.data.profile, client_id: app.globalData.clientId });
      const intent = ProfileManager.buildIntent(app.globalData.clientId, itemName, price);
      const merchantId = app.globalData.merchantId || 'box-001';
      const res = await dialogueAPI.start({
        intent,
        merchantId,
        openingText: `预算${price}元，能给我最优惠的${itemName}方案吗？`,
      });
      wx.hideLoading();
      this.setData({ isLoading: false });
      wx.navigateTo({
        url: `/pages/dialogue/dialogue?sessionId=${res.session_id}&itemName=${encodeURIComponent(itemName)}&merchantId=${merchantId}`,
      });
    } catch (err) {
      wx.hideLoading();
      this.setData({ isLoading: false });
      wx.showToast({ title: err.msg || '启动失败', icon: 'none' });
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

  // ─── 辅助 ───
  _addLog(type, text) {
    const logs = [...this.data.negotiationLog, { type, text, time: new Date().toLocaleTimeString() }];
    this.setData({ negotiationLog: logs.slice(-20) });
  },

  _showBestOffer(offer, itemName) {
    const merchantId = offer.merchant_id || 'box-001';
    wx.showModal({
      title: `🎉 最优报价 ¥${offer.final_price}`,
      content: `商家：${merchantId}\n${itemName} · 预计${offer.eta_minutes || 20}分钟\n满意度评分：${offer.match_score ? offer.match_score.toFixed(1) : '-'}`,
      confirmText: '接受并下单',
      cancelText: '继续谈判',
      confirmColor: '#30d158',
      success: (res) => {
        if (res.confirm) {
          // 跳转对话页查看详情
          wx.navigateTo({
            url: `/pages/dialogue/dialogue?sessionId=${offer.session_id || ''}&itemName=${encodeURIComponent(itemName)}&merchantId=${merchantId}&autoAccepted=1`,
          });
        }
      },
    });
  },

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
