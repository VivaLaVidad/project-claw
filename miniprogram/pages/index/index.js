// pages/index/index.js - C端发现页 v4.0（工业级，完整对齐后端协议）
const { createRequest, IntentAPI, DialogueAPI, AgentNegotiationAPI } = require('../../api/request');
const ProfileManager = require('../../utils/profile');

Page({
  data: {
    itemName: '',
    expectedPrice: '',
    isLoading: false,
    serverStatus: 'unknown',
    onlineMerchants: 0,
    recentOffers: [],
    profile: null,
    showProfilePanel: false,
    searchHistory: [],
    showHistory: false,
    // Agent 全自动谈判状态
    autoNegotiating: false,
    negotiationLog: [],
    negotiationResult: null,
  },

  _pollTimer: null,
  _request: null,

  onLoad() {
    const app = getApp();
    this._request = createRequest(app.globalData.serverBase, app.globalData.token);
    const profile = ProfileManager.loadClientProfile(app.globalData.clientId);
    const history = ProfileManager.getSearchHistory();
    this.setData({ profile, searchHistory: history });
    this._checkServerStatus();
  },

  onShow() { this._checkServerStatus(); },

  onUnload() {
    if (this._pollTimer) clearInterval(this._pollTimer);
  },

  // ── UI 事件 ──────────────────────────────────────────────
  onItemNameInput(e) {
    const val = e.detail.value;
    this.setData({ itemName: val, showHistory: val.length === 0 });
  },
  onPriceInput(e)   { this.setData({ expectedPrice: e.detail.value }); },
  onToggleProfile() { this.setData({ showProfilePanel: !this.data.showProfilePanel }); },
  onClearItem() { this.setData({ itemName: '', showHistory: true }); },

  onSelectHistory(e) {
    const item = e.currentTarget.dataset.item;
    this.setData({ itemName: item, showHistory: false });
  },

  onClearHistory() {
    ProfileManager.clearSearchHistory();
    this.setData({ searchHistory: [], showHistory: false });
  },

  onProfileChange(e) {
    const key = e.currentTarget.dataset.key;
    const raw = parseFloat(e.detail.value);
    const value = ['price_sensitivity','time_urgency','quality_preference'].includes(key)
      ? raw / 100 : raw;
    const profile = { ...this.data.profile, [key]: value };
    this.setData({ profile });
    ProfileManager.saveClientProfile(profile);
  },

  // ── 输入验证 ─────────────────────────────────────────────
  _validate() {
    const { itemName, expectedPrice } = this.data;
    if (!itemName.trim()) { wx.showToast({ title: '请输入商品名', icon: 'none' }); return false; }
    const price = parseFloat(expectedPrice);
    if (!price || price <= 0) { wx.showToast({ title: '请输入有效预算', icon: 'none' }); return false; }
    return { itemName: itemName.trim(), price };
  },

  // ── 核心1：Agent 全自动谈判 ──────────────────────────────
  async onAutoNegotiate() {
    const { isLoading, autoNegotiating } = this.data;
    if (isLoading || autoNegotiating) return;
    const v = this._validate();
    if (!v) return;

    const app = getApp();
    const agentAPI = AgentNegotiationAPI(this._request);
    const dialogueAPI = DialogueAPI(this._request);

    this.setData({ isLoading: true, autoNegotiating: true, negotiationLog: [], negotiationResult: null, recentOffers: [] });
    wx.showLoading({ title: 'Agent 砍价中...' });
    ProfileManager.addSearchHistory(v.itemName);

    try {
      // 1. 上传 C端画像
      await dialogueAPI.upsertClientProfile({
        ...this.data.profile,
        client_id: app.globalData.clientId,
      }).catch(() => {});
      this._addLog('info', '📋 C端画像已同步');

      // 2. 发起 A2A 全自动谈判
      const intentRes = await agentAPI.startAutoNegotiation({
        clientId:       app.globalData.clientId,
        itemName:       v.itemName,
        expectedPrice:  v.price,
        maxDistanceKm:  8.0,
        clientProfile:  this.data.profile,
      });
      this._addLog('agent', `🤖 意图已广播 #${(intentRes.intent_id||'').slice(0,8)}`);

      // 3. 直接返回 offers
      if (intentRes.offers && intentRes.offers.length > 0) {
        wx.hideLoading();
        this.setData({ isLoading: false, autoNegotiating: false, recentOffers: intentRes.offers });
        this._addLog('deal', `✅ 收到 ${intentRes.offers.length} 个报价`);
        ProfileManager.saveLocalOrder({
          intent_id: intentRes.intent_id, demand_text: v.itemName,
          max_price: v.price, status: 'offered', created_at: Date.now()/1000, location:'小程序',
        });
        this._showBestOffer(intentRes.offers[0], v.itemName);
        return;
      }

      // 4. 异步轮询（intent_id 存在时）
      const intentId = intentRes.intent_id;
      if (intentId) {
        this._addLog('info', '⏳ 正在与商家协商...');
        let polls = 0;
        this._pollTimer = setInterval(async () => {
          polls++;
          try {
            const result = await agentAPI.pollResult(intentId);
            if (result.status === 'completed' && result.best_offer) {
              clearInterval(this._pollTimer);
              wx.hideLoading();
              this.setData({
                isLoading: false, autoNegotiating: false,
                recentOffers: result.offers || [result.best_offer],
                negotiationResult: result.best_offer,
              });
              this._addLog('deal', `✅ 成交！¥${result.best_offer.final_price}`);
              ProfileManager.saveLocalOrder({
                intent_id: intentId, demand_text: v.itemName,
                max_price: v.price, status: 'executed',
                selected_offer: result.best_offer, created_at: Date.now()/1000, location:'小程序',
              });
              this._showBestOffer(result.best_offer, v.itemName);
            } else if (result.status === 'failed' || polls > 20) {
              clearInterval(this._pollTimer);
              wx.hideLoading();
              this.setData({ isLoading: false, autoNegotiating: false });
              this._addLog('warn', '⚠️ 暂无匹配商家，切换手动模式');
              this._fallbackToDialogue(v.itemName, v.price);
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

      // 5. 降级：跳转标准对话页
      wx.hideLoading();
      this.setData({ isLoading: false, autoNegotiating: false });
      this._fallbackToDialogue(v.itemName, v.price);
    } catch (err) {
      wx.hideLoading();
      this.setData({ isLoading: false, autoNegotiating: false });
      this._addLog('warn', `⚠️ ${err.msg || '自动谈判失败'}，切换手动模式`);
      this._fallbackToDialogue(v.itemName, v.price);
    }
  },

  // ── 核心2：快速广播（SignalingResponse 模型）────────────
  async onBroadcastIntent() {
    const v = this._validate();
    if (!v || this.data.isLoading) return;
    const app = getApp();
    const intentAPI = IntentAPI(this._request);
    this.setData({ isLoading: true });
    wx.showLoading({ title: '广播中...' });
    ProfileManager.addSearchHistory(v.itemName);
    try {
      const res = await intentAPI.broadcast({
        clientId:      app.globalData.clientId,
        location:      '小程序',
        demandText:    `想要${v.itemName}`,
        maxPrice:      v.price,
        timeout:       3.0,
        clientProfile: this.data.profile,
      });
      wx.hideLoading();
      const offers = res.offers || [];
      this.setData({ isLoading: false, recentOffers: offers });
      if (res.intent_id) {
        ProfileManager.saveLocalOrder({
          intent_id: res.intent_id, demand_text: v.itemName,
          max_price: v.price, status: offers.length > 0 ? 'offered' : 'broadcasted',
          created_at: Date.now()/1000, location:'小程序',
          responded: res.responded, total_merchants: res.total_merchants,
        });
      }
      if (offers.length === 0) wx.showToast({ title: `已广播给${res.total_merchants||0}个商家，暂无响应`, icon: 'none' });
      else this._showBestOffer(offers[0], v.itemName);
    } catch (err) {
      wx.hideLoading();
      this.setData({ isLoading: false });
      wx.showToast({ title: err.msg || '广播失败', icon: 'none' });
    }
  },

  // ── 核心3：手动对话 ──────────────────────────────────────
  async onStartDialogue() {
    const v = this._validate();
    if (!v || this.data.isLoading) return;
    this._fallbackToDialogue(v.itemName, v.price);
  },

  async _fallbackToDialogue(itemName, price) {
    const app = getApp();
    const dialogueAPI = DialogueAPI(this._request);
    this.setData({ isLoading: true });
    wx.showLoading({ title: '联系商家...' });
    try {
      await dialogueAPI.upsertClientProfile({ ...this.data.profile, client_id: app.globalData.clientId }).catch(() => {});
      const intent = ProfileManager.buildIntent(app.globalData.clientId, itemName, price);
      const merchantId = app.globalData.merchantId || 'box-001';
      const res = await dialogueAPI.start({
        intent, merchantId,
        openingText: `预算${price}元，能给我最优惠的${itemName}吗？`,
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

  // ── 辅助 ────────────────────────────────────────────────
  _addLog(type, text) {
    const logs = [...this.data.negotiationLog, { type, text, time: new Date().toLocaleTimeString() }];
    this.setData({ negotiationLog: logs.slice(-20) });
  },

  _showBestOffer(offer, itemName) {
    const merchantId = offer.merchant_id || 'box-001';
    wx.showModal({
      title: `🎉 最优报价 ¥${offer.final_price}`,
      content: `商家：${merchantId}\n${itemName} · 预计${offer.eta_minutes||20}分钟\n评分：${offer.match_score ? offer.match_score.toFixed(1) : '-'}`,
      confirmText: '接受并下单',
      cancelText:  '继续谈判',
      confirmColor: '#30d158',
      success: (res) => {
        if (res.confirm) {
          wx.navigateTo({
            url: `/pages/dialogue/dialogue?sessionId=${offer.session_id||''}&itemName=${encodeURIComponent(itemName)}&merchantId=${merchantId}&autoAccepted=1`,
          });
        }
      },
    });
  },

  async _checkServerStatus() {
    try {
      const sysAPI = require('../../api/request').SystemAPI(this._request);
      await sysAPI.health();
      this.setData({ serverStatus: 'online' });
      getApp().globalData.isConnected = true;
    } catch (e) {
      this.setData({ serverStatus: 'offline' });
      getApp().globalData.isConnected = false;
    }
  },
});
